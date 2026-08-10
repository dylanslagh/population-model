"""Phase 4 step 5: export all 236 UW locations, then check every one of them.

The single-country script reloads the 1.8 GB prediction objects on every call,
which is about ten hours for the full set. This drives the R loop that loads
them once instead, then does in Python everything the single-country path does:
builds each export's metadata, validates it, and records a checksum.

Two checks are worth naming because they are the reason to trust the result.

* **Equivalence.** The bulk R script is a second implementation of an already
  validated one. After the run, Finland and Nigeria are re-exported through the
  bulk path into a scratch directory and compared, byte for byte, with the
  exports the single-country script produced. Two paths that agree on nothing
  are two chances to be wrong.
* **Completeness.** The UW source has 236 locations and WPP has 237. The one
  absence must be Holy See and nothing else. That is asserted here rather than
  assumed, and it is the same reconciliation each individual export carries.

Resumable: a country whose export is already complete is skipped, so an
interrupted run continues where it stopped.

    python scripts/export_uw_all.py --rscript <path to Rscript.exe>
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import export_uw_fixture  # noqa: E402
from popmodel import paths  # noqa: E402
from popmodel.ingest.uw import UwExportError, validate_uw_export  # noqa: E402
from popmodel.sources import fetch, uw_extract, uw_wpp2024  # noqa: E402

HOLY_SEE = 336
COMPARED_FILES = ("trajectories.csv", "locations.csv", "shifts.csv")
EQUIVALENCE_COUNTRIES = (246, 566)


def write_iso3_map(destination: Path) -> dict[int, str]:
    """Hand R the country codes rather than letting it invent them."""
    source = paths.REFERENCE / "crosswalk.csv"
    mapping: dict[int, str] = {}
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = int(row["loc_id"])
            iso3 = str(row["iso3"]).strip().upper()
            if len(iso3) != 3:
                raise SystemExit(f"crosswalk has no usable ISO3 for LocID {code}")
            mapping[code] = iso3
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("loc_id", "iso3"))
        for code in sorted(mapping):
            writer.writerow((code, mapping[code]))
    return mapping


def run_extractor(rscript: Path, unpacked: dict, output_root: Path, iso3_map: Path,
                  only: tuple[int, ...] | None = None) -> None:
    extractor = paths.REPO_ROOT / "r" / "uw-extract" / "extract_all_countries.R"
    command = [
        str(rscript), "--vanilla", str(extractor),
        f"--tfr-dir={unpacked['tfr_annual'].simulation_dir}",
        f"--e0-dir={unpacked['e0_annual'].simulation_dir}",
        f"--output-root={output_root}",
        f"--iso3-map={iso3_map}",
    ]
    if only:
        command.append("--only=" + ",".join(str(code) for code in only))
    subprocess.run(command, check=True, cwd=paths.REPO_ROOT)


def finish_export(directory: Path, archive_sha256: dict, iso3_map: dict) -> dict:
    """Add the metadata the R side does not write, then validate the result."""
    loc_id = int(directory.name)
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        metadata = export_uw_fixture._build_metadata(
            directory,
            archive_sha256=archive_sha256,
            country_code=loc_id,
            iso3=iso3_map[loc_id],
        )
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    export = validate_uw_export(directory)
    return {
        "loc_id": export.loc_id,
        "iso3": export.iso3,
        "country": export.country,
        "trajectories_sha256": fetch.sha256_of(directory / "trajectories.csv"),
    }


def check_equivalence(rscript: Path, unpacked: dict, iso3_map_path: Path,
                      export_root: Path) -> list[str]:
    """Re-export two countries through the bulk path and compare byte for byte."""
    notes = []
    with tempfile.TemporaryDirectory(prefix="uw-equivalence-") as scratch:
        run_extractor(
            rscript, unpacked, Path(scratch), iso3_map_path, only=EQUIVALENCE_COUNTRIES
        )
        for code in EQUIVALENCE_COUNTRIES:
            reference = export_root / str(code)
            produced = Path(scratch) / str(code)
            if not reference.is_dir():
                notes.append(f"  LocID {code}: no single-country export to compare")
                continue
            for name in COMPARED_FILES:
                a = fetch.sha256_of(reference / name)
                b = fetch.sha256_of(produced / name)
                if a != b:
                    raise SystemExit(
                        f"the bulk and single-country exports disagree for LocID "
                        f"{code} in {name}\n  single: {a}\n  bulk:   {b}"
                    )
            notes.append(f"  LocID {code}: identical across both R paths")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rscript", help="path to R 4.4.2 Rscript.exe")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--min-free-gb", type=float, default=25.0)
    parser.add_argument(
        "--skip-equivalence", action="store_true",
        help="skip the byte-for-byte comparison against the single-country path",
    )
    args = parser.parse_args()

    export_root = args.output_root or (
        paths.INTERIM / uw_wpp2024.REVISION / "exports"
    )
    export_root.mkdir(parents=True, exist_ok=True)

    free = shutil.disk_usage(export_root).free
    needed = int(args.min_free_gb * 1024**3)
    if free < needed:
        raise SystemExit(
            f"only {free / 1024**3:.1f} GB free; the full export needs about "
            f"1.5 GB plus room for the unpacked archives"
        )

    unpacked = {
        item.key: item
        for item in uw_extract.unpack_uw_all(min_free_bytes=needed)
    }
    rscript = export_uw_fixture._rscript_path(args.rscript)
    export_uw_fixture._check_r_version(rscript)

    iso3_map_path = export_root.parent / "iso3-map.csv"
    iso3_map = write_iso3_map(iso3_map_path)

    started = time.time()
    run_extractor(rscript, unpacked, export_root, iso3_map_path)
    print(f"\nR export finished in {(time.time() - started) / 60:.1f} minutes")

    archive_sha256 = {
        key: unpacked[key].archive_sha256 for key in uw_wpp2024.REQUIRED_KEYS
    }
    directories = sorted(
        (d for d in export_root.glob("*") if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    print(f"validating {len(directories)} exports")
    records = []
    for index, directory in enumerate(directories, start=1):
        try:
            records.append(finish_export(directory, archive_sha256, iso3_map))
        except (UwExportError, RuntimeError) as exc:
            raise SystemExit(f"LocID {directory.name} failed validation: {exc}")
        if index % 40 == 0:
            print(f"  {index}/{len(directories)}")

    exported = {record["loc_id"] for record in records}
    if len(exported) != uw_wpp2024.EXPECTED_LOCATIONS:
        raise SystemExit(
            f"expected {uw_wpp2024.EXPECTED_LOCATIONS} UW locations, validated "
            f"{len(exported)}"
        )
    absent = sorted(set(iso3_map) - exported)
    if absent != [HOLY_SEE]:
        raise SystemExit(
            f"the only WPP location absent from UW must be Holy See ({HOLY_SEE}); "
            f"absent here: {absent}"
        )

    if not args.skip_equivalence:
        print("\nchecking the bulk path against the single-country path")
        for note in check_equivalence(rscript, unpacked, iso3_map_path, export_root):
            print(note)

    manifest = {
        "source_revision": uw_wpp2024.REVISION,
        "archive_sha256": archive_sha256,
        "locations": len(records),
        "trajectories_each": uw_wpp2024.EXPECTED_TRAJECTORIES,
        "years": [uw_wpp2024.TRAJECTORY_ANCHOR_YEAR, uw_wpp2024.FORECAST_END],
        "wpp_locations_absent": [HOLY_SEE],
        "equivalence_checked": not args.skip_equivalence,
        "exports": sorted(records, key=lambda record: record["loc_id"]),
    }
    paths.MANIFEST.mkdir(parents=True, exist_ok=True)
    out = paths.MANIFEST / "uw_wpp2024_full_export.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(records)} locations exported and validated")
    print(f"the only WPP location absent is Holy See ({HOLY_SEE}), as expected")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

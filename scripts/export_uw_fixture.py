"""Build and validate one country from UW's native Bayesian trajectory objects.

The default is Finland (LocID 246), the country used in UW's own archive
vignette.  The resulting CSV retains all 1,000 trajectories and the 2023 source
anchor; the Python draw adapter exposes only the 2024-2100 forecast years.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.ingest.uw import (  # noqa: E402
    COUPLING_METHOD,
    EXPECTED_ACCESSORS,
    EXPECTED_PACKAGE_REVISIONS,
    EXPECTED_PACKAGE_SOURCE_SHA256,
    EXPECTED_PACKAGE_SOURCES,
    EXPECTED_PACKAGES,
    EXPECTED_R_REPOSITORY,
    EXPECTED_R_VERSION,
    EXPORT_SCHEMA_VERSION,
    validate_uw_export,
)
from popmodel.sources import fetch, uw_extract, uw_wpp2024  # noqa: E402


def _iso3_for(loc_id: int) -> str:
    """The ISO3 code the rest of the project uses for this UN LocID.

    Derived from the committed crosswalk rather than passed in beside the
    country code. Two independent ways of naming the same country is one too
    many: a mismatched pair does not error anywhere downstream, it just
    silently projects one country using another country's schedules.
    """
    path = paths.REFERENCE / "crosswalk.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if int(row["loc_id"]) == loc_id:
                    code = str(row["iso3"]).strip().upper()
                    if len(code) != 3:
                        raise RuntimeError(
                            f"crosswalk has no usable ISO3 for LocID {loc_id}"
                        )
                    return code
    except FileNotFoundError as exc:
        raise RuntimeError(f"the country crosswalk is missing: {path}") from exc
    raise RuntimeError(
        f"LocID {loc_id} is not in {path.name}; refusing to guess an ISO3 code"
    )


def _rscript_path(argument: str | None) -> Path:
    candidates = []
    if argument:
        candidates.append(Path(argument))
    found = shutil.which("Rscript")
    if found:
        candidates.append(Path(found))
    candidates.append(Path(r"C:\Program Files\R\R-4.4.2\bin\Rscript.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "Rscript for R 4.4.2 was not found. Install the pinned reader environment "
        "described in r/uw-extract/README.md, or pass --rscript."
    )


def _check_r_version(rscript: Path) -> None:
    result = subprocess.run(
        [str(rscript), "--vanilla", "-e", "cat(as.character(getRversion()))"],
        check=True, capture_output=True, text=True,
    )
    actual = result.stdout.strip()
    if actual != EXPECTED_R_VERSION:
        raise RuntimeError(
            f"UW extraction requires R {EXPECTED_R_VERSION}; {rscript} is R {actual}"
        )


def _read_r_metadata(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != ("key", "value"):
            raise RuntimeError("R extractor metadata must have key and value columns")
        result: dict[str, str] = {}
        for row in reader:
            if row["key"] in result:
                raise RuntimeError(f"R extractor repeated metadata key {row['key']!r}")
            result[row["key"]] = row["value"]
    return result


def _integer(metadata: dict[str, str], key: str) -> int:
    try:
        return int(metadata[key])
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"R extractor did not report a valid {key}") from exc


def _build_metadata(
    directory: Path,
    *,
    archive_sha256: dict[str, str],
    country_code: int,
    iso3: str,
) -> dict:
    r_value = _read_r_metadata(directory / "r-metadata.tsv")
    expected_text = {
        "R_version": EXPECTED_R_VERSION,
        "bayesTFR_version": EXPECTED_PACKAGES["bayesTFR"],
        "bayesLife_version": EXPECTED_PACKAGES["bayesLife"],
        "iso3": iso3,
        "accessor_shifts_applied": "true",
    }
    for key, expected in expected_text.items():
        if r_value.get(key) != expected:
            raise RuntimeError(f"R extractor reported {key}={r_value.get(key)!r}, expected {expected!r}")
    expected_numbers = {
        "loc_id": country_code,
        "year_start": uw_wpp2024.TRAJECTORY_ANCHOR_YEAR,
        "year_end": uw_wpp2024.FORECAST_END,
        "year_count": uw_wpp2024.FORECAST_END - uw_wpp2024.TRAJECTORY_ANCHOR_YEAR + 1,
        "trajectories": uw_wpp2024.EXPECTED_TRAJECTORIES,
        "locations": uw_wpp2024.EXPECTED_LOCATIONS,
    }
    for key, expected in expected_numbers.items():
        if _integer(r_value, key) != expected:
            raise RuntimeError(f"R extractor reported an unexpected {key}")
    shift_keys = {
        "tfr": "tfr_shift_count",
        "e0_female": "e0_female_shift_count",
        "e0_male": "e0_male_shift_count",
    }
    shifts = {}
    for component, key in shift_keys.items():
        count = _integer(r_value, key)
        if count <= 0:
            raise RuntimeError(f"R extractor found no stored shift for {component}")
        shifts[component] = {
            "stored": True, "count": count, "applied_by_accessor": True
        }

    files = (
        "trajectories.csv", "locations.csv", "shifts.csv", "session-info.txt",
        "r-metadata.tsv",
    )
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "source_revision": uw_wpp2024.REVISION,
        "source_label": uw_wpp2024.REVISION_LABEL,
        "country": {
            "loc_id": country_code,
            "iso3": iso3,
            "name": r_value.get("country", "").strip(),
        },
        "years": {
            "source_start": uw_wpp2024.TRAJECTORY_ANCHOR_YEAR,
            "forecast_start": uw_wpp2024.FORECAST_START,
            "end": uw_wpp2024.FORECAST_END,
            "count": expected_numbers["year_count"],
        },
        "trajectories": uw_wpp2024.EXPECTED_TRAJECTORIES,
        "shape": [expected_numbers["year_count"], uw_wpp2024.EXPECTED_TRAJECTORIES],
        "trajectory_id_basis": (
            "one-based accessor column index; this is also the Trajectory value "
            "used by UW's official convert.*.trajectories functions"
        ),
        "R_version": EXPECTED_R_VERSION,
        "R_repository_snapshot": EXPECTED_R_REPOSITORY,
        "packages": EXPECTED_PACKAGES,
        "package_sources": EXPECTED_PACKAGE_SOURCES,
        "package_source_revisions": EXPECTED_PACKAGE_REVISIONS,
        "package_source_sha256": EXPECTED_PACKAGE_SOURCE_SHA256,
        "accessors": list(EXPECTED_ACCESSORS),
        "alignment_shifts": shifts,
        "coupling_method": COUPLING_METHOD,
        "archive_sha256": archive_sha256,
        "location_reconciliation": {
            "uw_count": uw_wpp2024.EXPECTED_LOCATIONS,
            "wpp_count": 237,
            "missing_wpp_loc_ids": [336],
        },
        "anchor_policy": (
            "2023 is retained as source evidence; model TrajectoryDraw objects "
            "begin at 2024"
        ),
        "file_sha256": {name: fetch.sha256_of(directory / name) for name in files},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country-code", type=int, default=246)
    parser.add_argument(
        "--iso3",
        help=(
            "optional cross-check; the ISO3 code is derived from the committed "
            "crosswalk and this must agree with it if given"
        ),
    )
    parser.add_argument("--rscript", help="path to R 4.4.2 Rscript.exe")
    parser.add_argument("--output", type=Path, help="output directory")
    parser.add_argument("--check-only", action="store_true", help="validate an existing export")
    parser.add_argument("--min-free-gb", type=float, default=25.0)
    args = parser.parse_args()
    iso3 = _iso3_for(args.country_code)
    if args.iso3 and args.iso3.strip().upper() != iso3:
        parser.error(
            f"--iso3={args.iso3.strip().upper()} disagrees with the crosswalk, "
            f"which has LocID {args.country_code} as {iso3}"
        )
    if args.min_free_gb < 0:
        parser.error("--min-free-gb cannot be negative")
    output = args.output or (
        paths.INTERIM / uw_wpp2024.REVISION / "exports" / str(args.country_code)
    )
    if args.check_only:
        value = validate_uw_export(output)
        print(f"ok: {value.country}, {len(value):,} trajectories, 2024-2100 model years")
        return 0
    if output.exists():
        raise RuntimeError(
            f"refusing to overwrite existing export {output}; validate it with --check-only"
        )

    unpacked = {
        item.key: item
        for item in uw_extract.unpack_uw_all(
            min_free_bytes=int(args.min_free_gb * 1024**3)
        )
    }
    rscript = _rscript_path(args.rscript)
    _check_r_version(rscript)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".staging-{args.country_code}-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        extractor = paths.REPO_ROOT / "r" / "uw-extract" / "extract_one_country.R"
        subprocess.run(
            [
                str(rscript), "--vanilla", str(extractor),
                f"--tfr-dir={unpacked['tfr_annual'].simulation_dir}",
                f"--e0-dir={unpacked['e0_annual'].simulation_dir}",
                f"--output-dir={staging}",
                f"--country-code={args.country_code}", f"--iso3={iso3}",
            ],
            check=True,
            cwd=paths.REPO_ROOT,
        )
        metadata = _build_metadata(
            staging,
            archive_sha256={
                key: unpacked[key].archive_sha256 for key in uw_wpp2024.REQUIRED_KEYS
            },
            country_code=args.country_code,
            iso3=iso3,
        )
        (staging / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        validate_uw_export(staging)
        staging.replace(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    value = validate_uw_export(output)
    print(f"ok: {value.country}, {len(value):,} trajectories exported to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

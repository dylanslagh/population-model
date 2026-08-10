"""Turn UW's bayesMig archive into the engine's migration assumption.

The archive is a plain CSV of net migration rates plus the R script that made
it, so unlike the fertility and mortality archives this one needs no R at all.

Three things happen here, in this order, because the third is only meaningful
if the first two hold:

1. The archive is fingerprinted and unpacked. Its SHA-256 goes in the manifest.
   UW publishes no checksum, so the recorded one is ours, of the file we used.
2. The rates are read and reduced to a median trajectory per country and year.
3. **The denominator is verified.** The archive does not say what population
   the rate is a rate of. Multiplying by each country's 1 January population
   must reproduce WPP's own published net migration figures, and this asserts
   that it does for the large migration countries before anything is written.

    python scripts/build_uw_migration.py --archive ~/Downloads/mig1trajWPP2024.tgz
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import tarfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_to_2150  # noqa: E402
from popmodel import paths  # noqa: E402
from popmodel.ingest import uw_mig, wpp  # noqa: E402
from popmodel.sources import fetch  # noqa: E402

ARCHIVE_URL = "https://bayespop.csss.washington.edu/data/bayesMig/mig1trajWPP2024.tgz"
ARCHIVE_BYTES = 94_281_648
MEMBER = "mig1traj/ascii_trajectories.csv"

# The countries the denominator check is asserted on: large absolute net
# migration, so the comparison is not dominated by rounding, and a mix of
# senders and receivers. bayesMig aligns its MEANS to WPP while this compares
# MEDIANS, so exact agreement is not expected -- gross disagreement is the
# thing being ruled out.
DENOMINATOR_CHECK = {
    840: "United States", 356: "India", 124: "Canada", 392: "Japan", 784: "UAE",
}
DENOMINATOR_TOLERANCE = 0.05


def unpack(archive: Path, destination: Path) -> Path:
    """Extract just the trajectory CSV, refusing anything that escapes."""
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "ascii_trajectories.csv"
    if target.exists():
        print(f"  already unpacked: {target}")
        return target
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.getmember(MEMBER)
        if not member.isfile():
            raise SystemExit(f"{MEMBER} is not a regular file")
        extracted = tar.extractfile(member)
        if extracted is None:
            raise SystemExit(f"could not read {MEMBER}")
        with extracted, target.open("wb") as handle:
            while chunk := extracted.read(1 << 20):
                handle.write(chunk)
    return target


def published_net_migration(year: int) -> dict[int, float]:
    """WPP's own net migration figures, for checking the rate's denominator."""
    path = paths.RAW / "WPP2024" / "WPP2024_Demographic_Indicators_Medium.csv.gz"
    result: dict[int, float] = {}
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("Time") == str(year):
                try:
                    result[int(row["LocID"])] = float(row["NetMigrations"]) * 1000.0
                except (KeyError, ValueError):
                    continue
    if not result:
        raise SystemExit(f"WPP publishes no net migration for {year}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()

    archive = args.archive.expanduser()
    if not archive.is_file():
        raise SystemExit(f"archive not found: {archive}")
    size = archive.stat().st_size
    if size != ARCHIVE_BYTES:
        raise SystemExit(
            f"{archive.name} is {size:,} bytes; the pinned archive is "
            f"{ARCHIVE_BYTES:,}. Refusing to use a different file."
        )
    digest = fetch.sha256_of(archive)
    print(f"archive:  {archive.name}")
    print(f"  bytes   {size:,}")
    print(f"  sha256  {digest}")

    csv_path = unpack(archive, paths.INTERIM / "UW_WPP2024" / "migration")
    print(f"\nreading {csv_path.name}")
    started = time.time()
    rates = uw_mig.read_trajectories(csv_path)
    print(
        f"  {len(rates.loc_id)} locations x {len(rates.years)} years "
        f"({time.time() - started:.0f}s)"
    )
    print(f"  median rate {rates.rates.min():+.4f} to {rates.rates.max():+.4f} per person")

    print("\nchecking what the rate is a rate of")
    bundle = wpp.load_bundle()
    published = published_net_migration(2024)
    pop_2024 = bundle.pop_base.sum(axis=(1, 2))
    rate_index = {int(code): i for i, code in enumerate(rates.loc_id)}
    year_index = int(np.where(rates.years == 2024)[0][0])
    failures = []
    for code, name in DENOMINATOR_CHECK.items():
        column = rate_index.get(code)
        row = int(np.where(bundle.loc_id == code)[0][0])
        implied = rates.rates[year_index, column] * pop_2024[row]
        actual = published[code]
        ratio = implied / actual
        status = "ok" if abs(ratio - 1.0) <= DENOMINATOR_TOLERANCE else "FAIL"
        print(
            f"  {status:>4}  {name:<14} implied {implied:>12,.0f}  "
            f"WPP {actual:>12,.0f}  ratio {ratio:.3f}"
        )
        if status == "FAIL":
            failures.append(name)
    if failures:
        raise SystemExit(
            f"the migration rate does not behave like a per-person rate for "
            f"{', '.join(failures)}. Do not guess the denominator; find out."
        )

    print("\nbacking out the age and sex composition from the UN's own residual")
    countries = pd.DataFrame(
        {"LocID": bundle.loc_id, "ISO3_code": bundle.iso3, "Location": bundle.name}
    )
    medium = wpp.medium_population(countries, bundle.years)
    residual = run_to_2150._derive_migration(bundle, medium)
    composition = uw_mig.age_sex_composition(residual)
    peak_age = int(np.argmax(composition.sum(axis=(0, 1))))
    female_share = float(composition[:, 0].sum() / composition.sum())
    print(f"  composition peaks at age {peak_age}; {female_share:.1%} female overall")

    population = medium.sum(axis=(2, 3))  # (Y, L) total population per year
    population_years = bundle.years[: population.shape[0]]
    print(
        f"  denominator path: {population.shape[0]} years, "
        f"{int(population_years[0])}-{int(population_years[-1])}"
    )

    path = uw_mig.save(
        rates, composition, bundle.iso3, population, population_years
    )
    manifest = {
        "source_label": uw_mig.SOURCE_LABEL,
        "archive": {
            "filename": archive.name,
            "url": ARCHIVE_URL,
            "bytes": size,
            "sha256": digest,
            "checksum_origin": "computed locally; UW publishes none",
        },
        "reduction": rates.provenance["reduction"],
        "denominator_check": {
            "year": 2024,
            "countries": sorted(DENOMINATOR_CHECK.values()),
            "tolerance": DENOMINATOR_TOLERANCE,
            "result": "rate x 1 January population reproduces WPP net migration",
        },
        "age_sex_composition": (
            "per-country shares from the UN's own medium-path migration "
            "residual, normalised over absolute flows; not independent evidence"
        ),
    }
    paths.MANIFEST.mkdir(parents=True, exist_ok=True)
    out = paths.MANIFEST / "uw_wpp2024_migration.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nwrote {path}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

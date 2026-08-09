"""Build the per-country files the map will load.

    python scripts/build_site_data.py

Needs the crosswalk (scripts/build_crosswalk.py) and the WPP bundle
(scripts/build_bundle.py). Takes a few minutes, mostly reading the historical
single-age file and running the projection to 2150.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import crosswalk, export, paths  # noqa: E402
from popmodel.engine import cohort  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_to_2150 import _derive_migration  # noqa: E402


def main() -> int:
    t0 = time.time()
    paths.ensure_dirs()
    bundle = wpp.load_bundle()
    countries = pd.DataFrame({
        "LocID": bundle.loc_id,
        "ISO3_code": bundle.iso3,
        "Location": bundle.name,
    })
    cw = crosswalk.load()

    print("Running the projection to 2150 (UN assumptions, migration from residual)...")
    medium = wpp.medium_population(countries, bundle.years)
    migration = _derive_migration(bundle, medium)
    run = cohort.project(
        bundle.pop_base,
        start_year=int(bundle.years[0]),
        sx=bundle.sx,
        asfr=bundle.asfr,
        srb=bundle.srb,
        migration=migration,
        locations=bundle.iso3,
        n_years=export.END_YEAR - int(bundle.years[0]),
    )

    print("Reading historical estimates 1950-2023...")
    data = export.build(bundle, countries, run)

    root = export.write(data, cw)
    files = list((root / "countries").glob("*.json"))
    size = sum(f.stat().st_size for f in files) + (root / "index.json").stat().st_size

    print(f"\n  {len(files)} country files + index.json, {size / 1e6:.1f} MB total")
    print(f"  pyramid years: {data.years[0]} to {data.years[-1]} every "
          f"{export.PYRAMID_STEP}, {len(data.years)} snapshots")
    print(f"  annual totals: {data.annual_years[0]} to {data.annual_years[-1]}")
    kinds = {k: data.kinds.count(k) for k in dict.fromkeys(data.kinds)}
    print(f"  year kinds: {kinds}")
    print(f"\nWrote {root.relative_to(paths.REPO_ROOT)} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

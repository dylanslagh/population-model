"""Build the data-confidence layer: when each country last counted its people.

    python scripts/build_census.py

Writes data/reference/census_dates.csv, which IS committed so the matching
decisions are reviewable as text. Raises rather than finish if any of the 237
countries is unaccounted for.

Spec section 4.5: show a data-confidence layer rather than greying countries
out. The point is not to mark some countries unreliable, it is that the map
otherwise presents a projection for Lebanon and a projection for Denmark in
exactly the same ink, and those two numbers are not the same kind of object.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.ingest import census, wpp  # noqa: E402

BANDS = ["within 5 years", "5 to 14 years", "15 years or more",
         "none since 1985", "not listed"]


def main() -> int:
    paths.ensure_dirs()
    countries = wpp.country_table()
    print("Matching UNSD census dates to WPP countries\n")
    df = census.load(countries)

    print(f"  {len(df)} countries, all accounted for\n")
    for band in BANDS:
        sub = df[df.band == band]
        print(f"  {len(sub):>3}  {band}")

    worst = df[df.band.isin(["none since 1985", "15 years or more"])]
    worst = worst.sort_values("last_census_year", na_position="first")
    print(f"\n  The {len(worst)} countries whose numbers rest on the least recent count:")
    for _, r in worst.iterrows():
        year = "no census since 1985" if r.last_census_year != r.last_census_year else int(r.last_census_year)
        print(f"    {r.iso3}  {r['name'][:38]:<38} {year}")

    path = census.table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"\nWrote {path.relative_to(paths.REPO_ROOT)}")
    print("\nThis measures ONE thing: how long since a census. It is not a data-quality")
    print("score. Denmark counts continuously from registers; a recent census can still")
    print("be bad. See src/popmodel/sources/unsd_census.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

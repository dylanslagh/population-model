"""Match every UN country to a shape on the map, and account for the rest.

    python scripts/build_crosswalk.py

Writes data/reference/crosswalk.csv, which IS committed, so that the decisions
about Kosovo, the French overseas departments and Gibraltar are reviewable as
text rather than buried in code. Raises rather than finish if any of the 237
countries is unaccounted for.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import crosswalk, paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    print("Joining UN countries to Natural Earth shapes\n")
    countries = wpp.country_table()
    cw = crosswalk.build(countries)

    t = cw.table
    print(f"  {len(t)} WPP countries and areas")
    print(f"  {cw.n_with_shape} have a shape, {int((~t.has_shape).sum())} do not\n")

    for kind, label in (
        ("matched", "matched on the UN numeric code"),
        ("matched_by_name", "matched by name (no UN code exists)"),
        ("point_only", "no shape at this resolution; drawn as a point"),
    ):
        sub = t[t.match == kind]
        print(f"  {len(sub):>3}  {label}")
        if kind != "matched":
            for _, r in sub.iterrows():
                print(f"         {r['iso3']}  {r['name']}  -  {r['reason']}")

    supplemented = t[t.reason.str.contains("overseas|Caribbean Netherlands|New Zealand territory",
                                           case=False, na=False)]
    if len(supplemented):
        print(f"\n  {len(supplemented)} taken from the finer map_units layer because the "
              "base layer\n  draws them inside their parent country:")
        for _, r in supplemented.iterrows():
            print(f"         {r['iso3']}  {r['name']}")

    print(f"\n  {len(cw.unmatched_shapes)} shapes on the map have no WPP population:")
    for x in cw.unmatched_shapes:
        print(f"         {x['name']}  -  {x['reason']}")

    path = crosswalk.save(cw)
    print(f"\nWrote {path.relative_to(paths.REPO_ROOT)}")
    print(f"      {(path.parent / 'crosswalk_no_population.csv').relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

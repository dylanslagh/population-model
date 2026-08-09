"""Simplify the country outlines and draw the result, so it can be looked at.

    python scripts/check_geometry.py [tolerance]

Writes out/geometry-check.png. The whole point is to open it: a simplification
tolerance that is slightly too high does not raise an error, it just quietly
turns Denmark into a triangle.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import crosswalk, geometry, paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402

TOLERANCE = 0.08  # degrees
MIN_AREA = 0.0


def rings_of(geom: dict):
    polys = ([geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"])
    for poly in polys:
        for ring in poly:
            yield ring


def main() -> int:
    tol = float(sys.argv[1]) if len(sys.argv) > 1 else TOLERANCE
    t0 = time.time()

    countries = wpp.country_table()
    cw = crosswalk.build(countries)
    print(f"{len(cw.shapes)} countries with shapes")

    simplified, before, after = geometry.simplify_all(cw.shapes, tol, MIN_AREA)
    print(f"tolerance {tol} degrees: {before:,} points -> {after:,} "
          f"({100 * after / before:.1f}%), {time.time() - t0:.0f}s")

    smallest = sorted(
        ((geometry.count_points(g), loc) for loc, g in simplified.items())
    )[:8]
    names = dict(zip(countries.LocID, countries.Location))
    print("fewest points after simplifying:")
    for n, loc in smallest:
        print(f"    {n:>4}  {names.get(loc, loc)}")

    fig, ax = plt.subplots(figsize=(15, 8), dpi=110)
    for loc, geom in simplified.items():
        for ring in rings_of(geom):
            xy = [geometry.equal_earth(lon, lat) for lon, lat in ring]
            ax.add_patch(MplPolygon(xy, closed=True, facecolor="#B5D4F4",
                                    edgecolor="#0C447C", linewidth=0.25))
    for _, r in cw.table[cw.table.match == "point_only"].iterrows():
        x, y = geometry.equal_earth(r.point_lon, r.point_lat)
        ax.plot([x], [y], marker="o", markersize=5, color="#D4537E", zorder=5)
        ax.annotate(r["name"], (x, y), xytext=(6, 4), textcoords="offset points",
                    fontsize=7, color="#993556")

    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.axis("off")
    ax.set_title(
        f"All {len(simplified)} country shapes, simplified to {tol}deg, Equal Earth projection",
        fontsize=11, color="#2C2C2A", loc="left")
    fig.tight_layout()

    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "geometry-check.png"
    fig.savefig(out, format="png", facecolor="white")
    plt.close(fig)
    print(f"\nWrote {out.relative_to(paths.REPO_ROOT)} - open it and look at it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

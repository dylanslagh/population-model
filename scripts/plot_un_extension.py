"""Plot the official 2100 boundary and the project-owned migration extension."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402

WATCH = ("ARE", "CAN", "USA", "JPN", "DEU", "NGA")
LABELS = {
    "ARE": "United Arab Emirates",
    "CAN": "Canada",
    "USA": "United States",
    "JPN": "Japan",
    "DEU": "Germany",
    "NGA": "Nigeria",
}
INK = "#252821"
BLUE = "#3977a8"
PALE = "#b9d4e8"


def main() -> int:
    source = paths.OUT / "un_project_extension_country_totals.npz"
    if not source.exists():
        raise FileNotFoundError("run scripts/run_un_extension.py first")
    z = np.load(source, allow_pickle=False)
    official_years = z["official_years"]
    official_world = z["official_world"] / 1e9
    years = z["extension_years"]
    world = z["world"] / 1e9
    q = np.quantile(world, (0.05, 0.5, 0.95), axis=0)
    locations = [str(v) for v in z["locations"]]
    location_q = z["location_quantiles"]
    levels = z["quantile_levels"]
    rows = [int(np.argmin(np.abs(levels - v))) for v in (0.05, 0.5, 0.95)]

    fig = plt.figure(figsize=(11.2, 7.2), facecolor="#faf9f5")
    grid = fig.add_gridspec(2, 1, height_ratios=(1.15, 1), hspace=0.52)

    ax = fig.add_subplot(grid[0])
    ax.set_facecolor("#faf9f5")
    ax.plot(official_years, official_world, color=INK, lw=2.2, label="UN WPP 2024")
    ax.fill_between(years, q[0], q[2], color=PALE, alpha=0.8, lw=0)
    ax.plot(years, q[1], color=BLUE, lw=2.2, label="project extension")
    ax.axvline(2100, color="#787c74", lw=1.2, ls="--")
    ax.text(2101.5, ax.get_ylim()[0] + 0.12, "UN boundary", color="#666a63", fontsize=9)
    ax.set_xlim(2024, 2150)
    ax.set_ylabel("world population, billions")
    ax.set_title(
        "The UN ends at 2100; the project extension begins there",
        loc="left",
        fontsize=14,
        y=1.12,
    )
    ax.text(
        0,
        1.035,
        "Post-2100 fertility and mortality are fixed; the blue range varies migration only.",
        transform=ax.transAxes,
        color="#666a63",
        fontsize=9.5,
    )
    ax.legend(frameon=False, loc="lower left", ncol=2)
    ax.grid(axis="y", color="#deddd7", lw=0.7)
    ax.spines[["top", "right"]].set_visible(False)

    ax = fig.add_subplot(grid[1])
    ax.set_facecolor("#faf9f5")
    y = np.arange(len(WATCH))
    for row, iso in enumerate(WATCH):
        j = locations.index(iso)
        base = location_q[rows[1], 0, j]
        values = location_q[rows, -1, j] / base * 100.0
        ax.plot([values[0], values[2]], [row, row], color=PALE, lw=7, solid_capstyle="round")
        ax.plot(values[1], row, "o", color=BLUE, ms=6)
    ax.axvline(100, color="#787c74", lw=1, ls=":")
    ax.set_xscale("log")
    ax.set_xlim(5, 2500)
    ax.set_xticks([10, 25, 50, 100, 250, 500, 1000, 2000])
    ax.get_xaxis().set_major_formatter(lambda value, _pos: f"{value:g}")
    ax.set_yticks(y, [LABELS[v] for v in WATCH])
    ax.invert_yaxis()
    ax.set_xlabel("2150 population as percent of its 2100 population (log scale)")
    ax.set_title("Migration uncertainty is narrow for the world and enormous for some countries", loc="left", fontsize=12)
    ax.grid(axis="x", color="#deddd7", lw=0.7)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)

    fig.text(
        0.01,
        0.01,
        "Lines show the 5th-95th percentile across 1,000 globally balanced migration paths; dots are medians. "
        "This is the project's AR(1) continuation of UW bayesMig output, not a UN projection after 2100.",
        fontsize=8.5,
        color="#666a63",
    )
    out_svg = paths.REPO_ROOT / "docs" / "un-project-extension.svg"
    out_png = paths.REPO_ROOT / "docs" / "un-project-extension.png"
    fig.savefig(out_svg, bbox_inches="tight")
    fig.savefig(out_png, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_svg.relative_to(paths.REPO_ROOT)}")
    print(f"wrote {out_png.relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

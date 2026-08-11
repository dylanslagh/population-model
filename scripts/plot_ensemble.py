"""Draw the ensemble: the world fan, and what migration does to countries.

Two panels, because they answer different questions.

The world fan is the project's central claim in one picture. At 2050 the band
is half a billion wide and by 2150 it spans seven billion, from a base that is
known to three significant figures. Nothing about the base data causes that.
It is one parameter nobody can measure -- where fertility settles -- and the
picture exists to make that obvious rather than to be read off.

The country panel is the honesty check on migration. Migration cancels
globally, so it is invisible in the world fan and decisive for individual
countries; showing both stops the first from being mistaken for the second.

    python scripts/plot_ensemble.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402

COUNTRIES = ("CAN", "USA", "JPN", "PHL")
BAND = "#4575b4"
MEDIAN = "#1a3a6b"


def load(name: str):
    totals = np.load(paths.OUT / f"{name}_country_totals.npz", allow_pickle=False)
    receipt = json.loads((paths.OUT / f"{name}.json").read_text(encoding="utf-8"))
    return totals, receipt


def main() -> int:
    totals, receipt = load("uw_ensemble")
    zero, _ = load("uw_ensemble_zero_migration")

    years = totals["years"]
    locations = [str(code) for code in totals["locations"]]
    quantiles = totals["location_quantiles"]  # (Q, Y, L)
    world = totals["world"]  # (D, Y)
    low, median, high = np.quantile(world, (0.05, 0.5, 0.95), axis=0) / 1e9

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2))

    ax = axes[0]
    ax.fill_between(years, low, high, color=BAND, alpha=0.22, lw=0,
                    label="90% of draws")
    ax.plot(years, median, color=MEDIAN, lw=2.2, label="median")
    ax.axvline(2100, color="0.55", lw=1, ls=":")
    ax.annotate(
        "UW's trajectories stop here;\nrates held constant after",
        xy=(2100, 0.6), xycoords=("data", "axes fraction"),
        xytext=(6, 0), textcoords="offset points",
        fontsize=7.5, color="0.35", va="center",
    )
    peak = int(years[np.argmax(median)])
    ax.plot([peak], [median.max()], "o", color=MEDIAN, ms=5)
    ax.annotate(
        f"median peaks at {median.max():.2f}bn in {peak}",
        xy=(peak, median.max()), xytext=(-4, 10), textcoords="offset points",
        fontsize=8, color=MEDIAN, ha="right",
    )
    # Zero baseline, deliberately. The band never approaches zero, so a
    # cropped axis would read as far more dramatic than it is; at full scale
    # the fan is still perfectly legible and the reader can see that the
    # spread, however wide, is a fraction of the total.
    ax.set_ylim(0, max(high) * 1.05)
    ax.set_xlim(years[0], years[-1])
    ax.set_ylabel("world population, billions")
    ax.set_xlabel("year")
    ax.set_title(
        f"World population, {receipt['draws']:,} posterior draws", fontsize=10.5
    )
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    index = {code: i for i, code in enumerate(locations)}
    zero_median = zero["location_quantiles"][1]
    for offset, code in enumerate(COUNTRIES):
        column = index[code]
        colour = plt.get_cmap("tab10")(offset)
        ax.plot(years, quantiles[1, :, column] / 1e6, color=colour, lw=1.9, label=code)
        ax.plot(
            years, zero_median[:, column] / 1e6, color=colour, lw=1.1, ls=(0, (2, 2))
        )
    ax.set_xlim(years[0], years[-1])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("population, millions")
    ax.set_xlabel("year")
    ax.set_title("Median country paths: solid with migration, dashed without", fontsize=10.5)
    ax.legend(fontsize=8, frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle(
        "The UN-equivalent baseline - UW's mean-reverting posterior, not this "
        "project's own view of 2150",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    paths.OUT.mkdir(parents=True, exist_ok=True)
    png = paths.OUT / "ensemble.png"
    fig.savefig(png, dpi=150)
    fig.savefig(paths.REPO_ROOT / "docs" / "ensemble.svg")
    plt.close(fig)
    print(f"wrote {png}")
    print(f"wrote {paths.REPO_ROOT / 'docs' / 'ensemble.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

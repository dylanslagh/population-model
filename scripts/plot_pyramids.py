"""Draw population pyramids from the exported country files.

    python scripts/plot_pyramids.py
    python scripts/plot_pyramids.py NGA IND JPN --years 1980 2024 2100 2150

A population pyramid is the whole model in one picture: a bar for every single
year of age, women on the left and men on the right, youngest at the bottom. A
country with lots of children has a wide base and looks like a pyramid. A
country that stopped having them looks like a mushroom, and eventually like a
column standing on a pin.

Writes both an SVG for the repo and a PNG, because the PNG can be opened and
looked at, and a figure nobody has looked at should not be shipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import export, paths  # noqa: E402

DOCS = paths.REPO_ROOT / "docs"

FEMALE_FILL = "#D4537E"
MALE_FILL = "#378ADD"
INK = "#2C2C2A"
MUTED = "#5F5E5A"
FAINT = "#D3D1C7"

KIND_LABEL = {
    "estimate": "estimated",
    "projection": "projected",
    "extension": "projected, past published rates",
}


def load_country(iso3: str) -> dict:
    p = export.out_dir() / "countries" / f"{iso3}.json"
    if not p.exists():
        raise SystemExit(f"{p} missing. Run: python scripts/build_site_data.py")
    return json.loads(p.read_text(encoding="utf-8"))


def draw(ax, country: dict, year: int, xmax: float) -> None:
    if year not in country["years"]:
        raise SystemExit(
            f"{country['iso3']} has no pyramid for {year}. Available: "
            f"{country['years'][0]}-{country['years'][-1]}, "
            f"mostly every {export.PYRAMID_STEP} years."
        )
    i = country["years"].index(year)
    ages = np.array(country["ages"])
    female = np.array(country["female"][i], dtype=float)
    male = np.array(country["male"][i], dtype=float)

    ax.barh(ages, -female / 1e6, height=1.0, color=FEMALE_FILL, linewidth=0)
    ax.barh(ages, male / 1e6, height=1.0, color=MALE_FILL, linewidth=0)
    ax.axvline(0, color=FAINT, linewidth=0.6)

    ax.set_xlim(-xmax, xmax)
    ax.set_ylim(-1, 101)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    # The top bar is everyone aged 100 or more piled together, so it can stick
    # out past the 99-year-olds. Labelling it stops that reading as a claim
    # that centenarians outnumber their juniors.
    ax.set_yticklabels(["0", "20", "40", "60", "80", "100+"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(FAINT)
    ax.tick_params(colors=MUTED, labelsize=8, length=3)
    ax.grid(axis="x", color=FAINT, linewidth=0.4, alpha=0.6)
    ax.set_axisbelow(True)

    # Absolute values on the axis: the left side is women, not negative people.
    ticks = ax.get_xticks()
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{abs(t):g}" for t in ticks])

    total = (female.sum() + male.sum()) / 1e6
    kind = KIND_LABEL[country["kinds"][i]]
    ax.set_title(f"{year}  ·  {total:,.0f}m\n{kind}", color=INK, fontsize=9,
                 loc="left", pad=6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("countries", nargs="*", default=["NGA", "IND", "JPN"])
    ap.add_argument("--years", nargs="*", type=int, default=[1980, 2024, 2100, 2150])
    args = ap.parse_args()

    isos = args.countries or ["NGA", "IND", "JPN"]
    years = args.years
    data = [load_country(iso) for iso in isos]

    fig, axes = plt.subplots(len(isos), len(years),
                             figsize=(2.9 * len(years), 3.0 * len(isos)), dpi=150)
    axes = np.atleast_2d(axes)

    for r, country in enumerate(data):
        # One x-scale per country, so the shape change over time is honest:
        # a shrinking pyramid should look smaller, not be rescaled to fill.
        biggest = 0.0
        for y in years:
            if y not in country["years"]:
                raise SystemExit(f"no pyramid for {y}; available {country['years']}")
            i = country["years"].index(y)
            biggest = max(biggest, max(country["female"][i]), max(country["male"][i]))
        xmax = (biggest / 1e6) * 1.12

        for c, y in enumerate(years):
            draw(axes[r, c], country, y, xmax)
            if c == 0:
                axes[r, c].set_ylabel(f"{country['name']}\nage", color=INK, fontsize=10)
            if r == len(data) - 1:
                axes[r, c].set_xlabel("millions of people", color=MUTED, fontsize=8.5)

    fig.suptitle("Population pyramids: women on the left, men on the right",
                 color=INK, fontsize=13, x=0.006, ha="left", y=0.995)
    fig.text(0.5, 0.005,
             "Each bar is one year of age; the top bar is everyone 100 and over. "
             "Estimates to 2023 are the UN's, everything after is this project's engine.",
             ha="center", color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.022, 1, 0.965))

    DOCS.mkdir(parents=True, exist_ok=True)
    stem = "pyramids-" + "-".join(i.lower() for i in isos)
    svg = DOCS / f"{stem}.svg"
    png = paths.OUT / f"{stem}.png"
    paths.OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(svg, format="svg", transparent=True)
    fig.savefig(png, format="png", facecolor="white")
    plt.close(fig)

    print(f"Wrote {svg.relative_to(paths.REPO_ROOT)}")
    print(f"      {png.relative_to(paths.REPO_ROOT)}  (for looking at)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

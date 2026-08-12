"""Frames for a population bar-chart race, 1950 to 2100.

The genre is well worn — biggest companies, biggest cities — and the reason to
make another one is that every existing population version draws a single
confident line. This one shows the uncertainty, and shows it appearing.

Through 1950-2023 the bars are solid: those are the UN's reconstruction of what
already happened. From 2024 a whisker appears on each bar and grows, because
from there the figures are a projection and the 1,000 posterior draws disagree.
Nobody has to explain that on screen. The whiskers arriving in 2024 and widening
year by year *is* the explanation.

It stops at 2100, which is where the UN's own assumptions stop. Everything this
project does beyond that is its own extrapolation and does not belong in a video
whose legitimacy comes from the source.

Writes numbered PNGs. There is no encoder on this machine, so turning them into
a video is a separate step: any editor will import an image sequence, or
ffmpeg will do it in one line (printed at the end).

    python scripts/render_race.py --still 2065      # one frame, to look at
    python scripts/render_race.py                   # the whole sequence
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

START, END = 1950, 2100
BARS = 12
FPS = 30
YEARS_PER_SECOND = 4.0

# Region colours, assigned by hand for the ~30 countries that ever reach the top
# twelve. This is presentation, not data: no number here comes from it.
REGION = {
    "CHN": "east", "IND": "south", "USA": "west", "IDN": "east", "PAK": "south",
    "NGA": "africa", "BRA": "latin", "BGD": "south", "RUS": "west", "MEX": "latin",
    "JPN": "east", "ETH": "africa", "PHL": "east", "EGY": "africa", "VNM": "east",
    "COD": "africa", "TUR": "west", "IRN": "south", "DEU": "west", "THA": "east",
    "TZA": "africa", "FRA": "west", "GBR": "west", "ITA": "west", "ZAF": "africa",
    "MMR": "east", "KEN": "africa", "KOR": "east", "COL": "latin", "ESP": "west",
    "UGA": "africa", "SDN": "africa", "NER": "africa", "AGO": "africa",
    "UKR": "west", "POL": "west", "ARG": "latin", "DZA": "africa", "IRQ": "south",
    "AFG": "south", "MOZ": "africa", "GHA": "africa", "YEM": "south",
    "MDG": "africa", "CIV": "africa", "CMR": "africa", "MLI": "africa",
    "BFA": "africa", "MWI": "africa", "ZMB": "africa", "SOM": "africa",
    "SEN": "africa", "TCD": "africa", "GIN": "africa", "RWA": "africa",
    "BEN": "africa", "BDI": "africa", "TUN": "africa", "SSD": "africa",
    "NPL": "south", "UZB": "south", "SAU": "south", "MAR": "africa",
    "PER": "latin", "VEN": "latin", "CAN": "west", "AUS": "west",
}
COLOUR = {
    "africa": "#c1553b", "south": "#2f6f9f", "east": "#d9a441",
    "west": "#6a7f8c", "latin": "#5d8a5e", "other": "#9aa5ad",
}
NAMES = {"COD": "DR Congo", "USA": "United States", "GBR": "United Kingdom",
         "RUS": "Russia", "IRN": "Iran", "TZA": "Tanzania", "KOR": "South Korea",
         "VNM": "Viet Nam", "SSD": "South Sudan"}


def load_series():
    """Annual totals per country, plus the ensemble's 5th and 95th percentiles."""
    root = export.out_dir()
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    first = index["annual_years"][0]
    totals, names = {}, {}
    for row in index["countries"]:
        iso = row["iso3"]
        payload = json.loads(
            (root / "countries" / f"{iso}.json").read_text(encoding="utf-8")
        )
        totals[iso] = np.array(payload["annual_total"], dtype=float)
        names[iso] = NAMES.get(iso, payload["name"])

    band = {}
    path = paths.OUT / "uw_ensemble_country_totals.npz"
    if path.exists():
        z = np.load(path, allow_pickle=False)
        years = z["years"]
        codes = [str(c) for c in z["locations"]]
        q = z["location_quantiles"]
        band = {
            code: (q[0, :, j], q[-1, :, j], int(years[0]))
            for j, code in enumerate(codes)
        }
    return totals, names, first, band


def frame(year: float, totals, names, first, band, ax):
    """One frame. Fractional years are interpolated so the bars glide."""
    lower, upper = int(np.floor(year)), int(np.ceil(year))
    blend = year - lower

    def value(iso, series, offset):
        a = series[min(lower - offset, len(series) - 1)]
        b = series[min(upper - offset, len(series) - 1)]
        return a + (b - a) * blend

    rows = []
    for iso, series in totals.items():
        if lower - first < 0:
            continue
        total = value(iso, series, first)
        lo = hi = None
        if iso in band and year >= band[iso][2]:
            lo = value(iso, band[iso][0], band[iso][2])
            hi = value(iso, band[iso][1], band[iso][2])
        rows.append((total, iso, lo, hi))
    rows.sort(reverse=True)
    rows = rows[:BARS][::-1]

    ax.clear()
    y = np.arange(len(rows))
    values = [r[0] / 1e6 for r in rows]
    colours = [COLOUR[REGION.get(r[1], "other")] for r in rows]
    ax.barh(y, values, color=colours, height=0.78)

    # The axis has to hold the widest whisker, not the widest bar, or the
    # uncertainty silently runs off the edge exactly where it is largest.
    reach = max(
        [r[0] for r in rows] + [r[3] for r in rows if r[3] is not None]
    ) / 1e6

    for i, (total, iso, lo, hi) in enumerate(rows):
        if lo is not None and hi > lo:
            ax.plot([lo / 1e6, hi / 1e6], [i, i], color="#2b2b2b", lw=1.4, alpha=0.55,
                    solid_capstyle="butt")
            for edge in (lo, hi):
                ax.plot([edge / 1e6, edge / 1e6], [i - 0.2, i + 0.2],
                        color="#2b2b2b", lw=1.4, alpha=0.55)
        # The value sits past whatever is furthest right on this row, so it
        # never lands on top of the whisker it is describing.
        edge = max(total, hi if hi is not None else total) / 1e6
        ax.text(edge + reach * 0.015, i, f"{total/1e6:,.0f}",
                ha="left", va="center", fontsize=12.5, color="#3a3a3a")

    ax.set_xlim(0, reach * 1.20)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_yticks(y)
    ax.set_yticklabels([names[r[1]] for r in rows], fontsize=13.5, color="#2b2b2b")
    ax.tick_params(axis="y", length=0, pad=8)
    ax.set_xlabel("population, millions", fontsize=11, color="#555")
    ax.tick_params(axis="x", colors="#777", labelsize=10)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#ccc")

    ax.text(0.985, 0.10, f"{int(year)}", transform=ax.transAxes, ha="right",
            fontsize=54, fontweight="700", color="#d8d8d8", zorder=0)
    kind = "UN estimates" if year < 2024 else "UN projection, with 90% of 1,000 draws"
    ax.text(0.985, 0.045, kind, transform=ax.transAxes, ha="right",
            fontsize=11, color="#9a9a9a", zorder=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--still", type=int, action="append",
                        help="render one year and stop; repeatable")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    totals, names, first, band = load_series()
    out = args.out or (paths.OUT / "race")
    out.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    fig.subplots_adjust(left=0.135, right=0.965, top=0.92, bottom=0.11)
    fig.suptitle("The twelve most populous countries, 1950 to 2100",
                 fontsize=17, fontweight="600", x=0.02, ha="left")

    if args.still:
        for year in args.still:
            frame(float(year), totals, names, first, band, ax)
            path = out / f"still-{year}.png"
            fig.savefig(path, facecolor="white")
            print(f"wrote {path}")
        return 0

    step = YEARS_PER_SECOND / FPS
    years = np.arange(START, END + step / 2, step)
    print(f"rendering {len(years)} frames at {FPS} fps "
          f"({len(years)/FPS:.0f} seconds of video)")
    for n, year in enumerate(years):
        frame(float(year), totals, names, first, band, ax)
        fig.savefig(out / f"frame-{n:05d}.png", facecolor="white")
        if n % 200 == 0:
            print(f"  {n}/{len(years)}")
    plt.close(fig)
    print(f"\nwrote {len(years)} frames to {out}")
    print("There is no encoder on this machine. To make an MP4:")
    print(f'  ffmpeg -framerate {FPS} -i "{out}/frame-%05d.png" '
          f'-c:v libx264 -pix_fmt yuv420p -crf 18 race.mp4')
    print("or import the folder as an image sequence in any video editor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

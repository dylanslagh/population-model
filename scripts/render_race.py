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

Writes numbered 1920x1080 PNGs and, with --encode, an H.264 MP4. ffmpeg is a
portable build kept outside the repository beside R and Tectonic; its path is in
LOCAL_TOOLS.md and is passed with --ffmpeg or the FFMPEG environment variable,
so nothing here depends on ffmpeg being installed anywhere in particular.

    python scripts/render_race.py --still 2065      # one frame, to look at
    python scripts/render_race.py --encode          # the sequence, then the MP4
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
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
YEARS_PER_SECOND = 1.5  # 1950-2100 in about 100 seconds
DPI = 150  # 12.8x7.2 inches -> 1920x1080, which is what YouTube wants

# Without these the last year is on screen for one frame and nobody can read the
# ending. Held in the encoder rather than by writing duplicate PNGs, so the frame
# folder stays a plain one-frame-per-instant sequence for any other editor.
HOLD_START, HOLD_END = 1.5, 4.0

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

    ax.text(0.985, 0.135, f"{int(year)}", transform=ax.transAxes, ha="right",
            fontsize=54, fontweight="700", color="#d8d8d8", zorder=0)
    # The bar and the whisker do not come from the same place, and saying they
    # do would be the one dishonesty this video cannot afford. The bar is the
    # UN's own figures; the whisker is the University of Washington's Bayesian
    # posterior, which is a separate publication even though the UN's own
    # probabilistic work uses that group's method.
    kind = ("UN estimates" if year < 2024 else
            "UN medium projection; whiskers are 90% of 1,000 draws\n"
            "from the University of Washington's Bayesian posterior")
    ax.text(0.985, 0.038, kind, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=10, color="#9a9a9a", linespacing=1.45, zorder=0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--still", type=int, action="append",
                        help="render one year and stop; repeatable")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--encode", action="store_true",
                        help="run ffmpeg on the frames when they are done")
    parser.add_argument("--encode-only", action="store_true",
                        help="skip rendering and encode the frames already there")
    parser.add_argument("--ffmpeg", type=Path,
                        help="path to ffmpeg.exe; defaults to $FFMPEG then PATH")
    args = parser.parse_args()

    out = args.out or (paths.OUT / "race")
    out.mkdir(parents=True, exist_ok=True)
    mp4 = out.parent / "race-1950-2100.mp4"

    if args.encode_only:
        return encode(out, mp4, args.ffmpeg)

    totals, names, first, band = load_series()

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=DPI)
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

    # linspace, not arange. Stepping by YEARS_PER_SECOND/FPS accumulates float
    # error until the last value is 2099.9999999998, which int() floors to 2099:
    # a video titled "1950 to 2100" that never shows 2100, and every year label
    # arriving one frame late. linspace pins both ends exactly.
    steps = round((END - START) * FPS / YEARS_PER_SECOND)
    years = np.linspace(START, END, steps + 1)
    assert years[0] == START and years[-1] == END
    print(f"rendering {len(years)} frames at {FPS} fps "
          f"({len(years)/FPS:.0f} seconds of video)")
    for n, year in enumerate(years):
        frame(float(year), totals, names, first, band, ax)
        fig.savefig(out / f"frame-{n:05d}.png", facecolor="white")
        if n % 200 == 0:
            print(f"  {n}/{len(years)}")
    plt.close(fig)
    print(f"\nwrote {len(years)} frames to {out}")

    if args.encode:
        return encode(out, mp4, args.ffmpeg)
    print("To make an MP4:")
    print(f"  python scripts/render_race.py --encode --out {out}")
    print("or import the folder as an image sequence in any video editor.")
    return 0


def encode(frames: Path, mp4: Path, ffmpeg: Path | None) -> int:
    """Frames to H.264. Fails loudly rather than writing a truncated file."""
    exe = str(ffmpeg or os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "")
    if not exe or not (Path(exe).exists() or shutil.which(exe)):
        raise SystemExit(
            "no ffmpeg. Pass --ffmpeg, set $FFMPEG, or put it on PATH. "
            "LOCAL_TOOLS.md records where the portable build lives."
        )
    count = len(sorted(frames.glob("frame-*.png")))
    if count == 0:
        raise SystemExit(f"no frames in {frames}; render them first")
    pad = (f"tpad=start_mode=clone:start_duration={HOLD_START}"
           f":stop_mode=clone:stop_duration={HOLD_END}")
    cmd = [
        exe, "-y", "-framerate", str(FPS),
        "-i", str(frames / "frame-%05d.png"),
        "-vf", pad,
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        # YouTube re-encodes whatever it is given, so the job here is to hand it
        # something lossless-looking. yuv420p is the only chroma format every
        # player accepts, and faststart moves the index to the front so the file
        # can be scrubbed before it has finished downloading.
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(mp4),
    ]
    print(f"encoding {count} frames -> {mp4}")
    subprocess.run(cmd, check=True)
    size = mp4.stat().st_size / 1e6
    seconds = count / FPS + HOLD_START + HOLD_END
    print(f"wrote {mp4} ({size:.1f} MB, {seconds:.0f} seconds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""YouTube thumbnail: the video's first frame, with a headline beside it.

1280x720, which is what YouTube asks for. The chart is squeezed into the left
half and the right half carries the text, because a thumbnail is read at about
360 pixels wide in a sidebar and the chart at that size is texture rather than
information. The text has to do the work.

The frame itself is drawn by `render_race.frame`, not reimplemented here, so the
thumbnail cannot drift away from the video it is advertising. Its own year
watermark and source caption are removed: at thumbnail size they are unreadable
clutter, and the headline says the year anyway.

    python scripts/render_thumbnail.py            # every variant
    python scripts/render_thumbnail.py --variant plain
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import render_race  # noqa: E402
from popmodel import paths  # noqa: E402

YEAR = 1950  # the video's first frame
INK = "#1d1d1d"
MUTED = "#7d7d7d"

# Each variant is (headline lines, the small line under the rule, accent colour).
# The accent colours are the video's own region palette, so the thumbnail and the
# bars beside it belong to the same picture.
VARIANTS = {
    "takeover": (
        ["1950", "→ 2100"],
        "the twelve biggest countries,\nand who takes over",
        render_race.COLOUR["south"],
    ),
    "uncertainty": (
        ["NOBODY", "KNOWS", "2100"],
        "so this one shows you\nhow much nobody knows",
        render_race.COLOUR["africa"],
    ),
    "plain": (
        ["150 YEARS", "OF WORLD", "POPULATION"],
        "UN figures, with the\nuncertainty left in",
        render_race.COLOUR["east"],
    ),
}


def fit_fontsize(fig, lines: list[str], x: float, right: float,
                 start: float = 68.0) -> float:
    """Largest size at which the longest line still fits the text column.

    Hard-coding a size means a longer headline silently runs off the right edge
    of the canvas, which is invisible in the log and obvious in the file.
    """
    renderer = fig.canvas.get_renderer()
    available = (right - x) * fig.get_figwidth() * fig.dpi
    widest = 0.0
    for line in lines:
        probe = fig.text(0, -1, line, fontsize=start, fontweight="800")
        widest = max(widest, probe.get_window_extent(renderer).width)
        probe.remove()
    return start * min(1.0, available / widest)


def render(name: str, out: Path) -> Path:
    lines, sub, accent = VARIANTS[name]
    totals, names, first, band = render_race.load_series()

    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    # The chart stops at 0.52 so nothing it draws can run under the headline.
    fig.subplots_adjust(left=0.135, right=0.52, top=0.94, bottom=0.10)
    render_race.frame(float(YEAR), totals, names, first, band, ax)

    # frame() ends by adding the year watermark and the source caption. They are
    # the last two texts on the axes and are noise at this size.
    for text in ax.texts[-2:]:
        text.remove()
    ax.set_xlabel("")
    ax.tick_params(axis="x", labelsize=8)
    for label in ax.get_yticklabels():
        label.set_fontsize(11)

    x, right = 0.575, 0.97
    size = fit_fontsize(fig, lines, x, right)
    step = 0.175 * size / 68

    # Centre the block vertically on the number of lines it actually has, or a
    # two-line headline leaves a third of the thumbnail empty at the bottom.
    block = len(lines) * step + 0.19
    y = 0.5 + block / 2
    drawn = []
    for line in lines:
        drawn.append(fig.text(x, y, line, fontsize=size, fontweight="800",
                              color=INK, ha="left", va="top"))
        y -= step

    y -= 0.02
    fig.add_artist(plt.Line2D([x, x + 0.20], [y, y], color=accent, lw=7,
                              transform=fig.transFigure))
    fig.text(x, y - 0.055, sub, fontsize=21, color=MUTED, ha="left", va="top",
             linespacing=1.35)

    # Belt and braces on the fit above: measure what was actually drawn and
    # refuse to write a thumbnail whose headline is cut off. A cropped word is
    # perfectly plausible in a log and only visible if somebody opens the file.
    renderer = fig.canvas.get_renderer()
    width = fig.get_figwidth() * fig.dpi
    for text in drawn:
        box = text.get_window_extent(renderer)
        if box.x1 > width + 1:
            raise SystemExit(
                f"headline {text.get_text()!r} runs {box.x1 - width:.0f}px past "
                f"the edge of the {name} thumbnail"
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    size = out.stat().st_size / 1e6
    if size > 2.0:  # YouTube's hard limit
        raise SystemExit(f"{out} is {size:.1f} MB; YouTube rejects over 2 MB")
    print(f"wrote {out} ({size * 1000:.0f} KB)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", choices=sorted(VARIANTS))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    chosen = [args.variant] if args.variant else sorted(VARIANTS)
    for name in chosen:
        out = args.out or (paths.OUT / "thumbnails" / f"thumbnail-{name}.png")
        render(name, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

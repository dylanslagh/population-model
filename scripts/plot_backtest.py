"""Draw the backtest.

    python scripts/plot_backtest.py

Two figures, both generated from out/backtest_*.csv, which are generated from
the archives. No number in either is typed by hand.

  docs/backtest-world-population.svg
      Every vintage's projection of world population, against what happened.

  docs/backtest-fertility.svg
      The two fertility failures, which are what actually drove the population
      misses: Africa's decline projected too fast, East Asia's floor assumed
      too high.

Design notes: bars and axes start at a sensible baseline and the population
axis is not truncated, because the size of the gap is the point. The vintage
lines are drawn in one colour ramp ordered by year so the reader can see the
UN swinging from over- to under-projection without needing the legend.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402

DOCS = paths.REPO_ROOT / "docs"

INK = "#2C2C2A"
MUTED = "#5F5E5A"
FAINT = "#D3D1C7"
ACTUAL = "#0C447C"
OVER = "#993C1D"
UNDER = "#0F6E56"


def _make_theme_aware(path: Path) -> None:
    """Let the figure survive a dark background.

    Matplotlib writes fixed colours as presentation attributes. A CSS rule beats
    a presentation attribute, so injecting one stylesheet is enough to flip the
    text and the axis furniture in dark mode while leaving the data colours -
    which were chosen to work on either - alone. Without this the title and the
    axis labels are near-black on near-black for anyone reading in dark mode,
    which is most people looking at a repo at night.
    """
    css = (
        "<style>@media (prefers-color-scheme: dark){"
        "text{fill:#E8E6E1 !important}"
        "}</style>"
    )
    body = path.read_text(encoding="utf-8")
    marker = ">"
    idx = body.index("<svg")
    insert_at = body.index(marker, idx) + 1
    path.write_text(body[:insert_at] + css + body[insert_at:], encoding="utf-8")


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(FAINT)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=FAINT, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    # Years are integers. Matplotlib will happily label one "2007.5".
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=7))


def world_population_figure(pop: pd.DataFrame) -> Path:
    w = pop[pop.loc_id == 900].copy()
    vintages = sorted(w.vintage.unique())
    cmap = plt.get_cmap("viridis")

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.2, 5.0), dpi=140)
    _style(ax)
    _style(bx)

    for i, v in enumerate(vintages):
        s = w[w.vintage == v].sort_values("period_start")
        colour = cmap(0.08 + 0.78 * i / max(1, len(vintages) - 1))
        ax.plot(s.period_start, s.projected / 1e9, marker="o", markersize=3.2,
                linewidth=1.4, color=colour, label=f"WPP {int(v)}", zorder=2)
        bx.plot(s.period_start, s.rel_error * 100, marker="o", markersize=3.2,
                linewidth=1.4, color=colour, zorder=2)

    actual = w.drop_duplicates("period_start").sort_values("period_start")
    ax.plot(actual.period_start, actual.actual / 1e9, color=ACTUAL, linewidth=2.8,
            zorder=3, label="what happened\n(WPP 2024 estimate)")

    ax.set_xlabel("year being projected", color=MUTED, fontsize=10)
    ax.set_ylabel("world population (billions)", color=MUTED, fontsize=10)
    ax.set_title("What each revision said", color=INK, fontsize=12, loc="left", pad=10)
    ax.legend(frameon=False, fontsize=8, labelcolor=MUTED, ncol=2,
              loc="upper left", bbox_to_anchor=(0.005, 0.995))

    # The error panel is the honest one: it has a real zero and the vertical
    # axis is not doing any persuading. The level panel on the left is
    # necessarily truncated, because a zero-based population axis would squash
    # every difference in the figure into the thickness of the line.
    bx.axhline(0, color=ACTUAL, linewidth=2.0, zorder=3)
    bx.set_xlabel("year being projected", color=MUTED, fontsize=10)
    bx.set_ylabel("how far off, per cent", color=MUTED, fontsize=10)
    bx.set_title("How far off it was", color=INK, fontsize=12, loc="left", pad=10)
    lim = max(4.8, float((w.rel_error.abs().max() * 100) * 1.15))
    bx.set_ylim(-lim, lim)
    bx.annotate("too many people", xy=(0.985, 0.94), xycoords="axes fraction",
                ha="right", color=OVER, fontsize=9)
    bx.annotate("too few people", xy=(0.985, 0.04), xycoords="axes fraction",
                ha="right", color=UNDER, fontsize=9)

    fig.suptitle("Thirty years of UN world population projections, marked",
                 color=INK, fontsize=13.5, x=0.008, ha="left", y=0.985)
    fig.text(0.5, 0.015,
             "Each thin line is one revision's medium projection, shown only for years that "
             "have since arrived. Left-hand axis is truncated; the right-hand one is not.",
             ha="center", color=MUTED, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))

    out = DOCS / "backtest-world-population.svg"
    fig.savefig(out, format="svg", transparent=True)
    plt.close(fig)
    _make_theme_aware(out)
    return out


def fertility_figure(tfr: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.4), dpi=140, sharey=False)
    panels = [
        (903, "Africa", "decline projected too fast", axes[0]),
        (906, "Eastern Asia", "floor assumed near replacement", axes[1]),
    ]
    cmap = plt.get_cmap("viridis")
    for loc, name, subtitle, ax in panels:
        s = tfr[tfr.loc_id == loc].copy()
        _style(ax)
        vintages = sorted(s.vintage.unique())
        for i, v in enumerate(vintages):
            sub = s[s.vintage == v].sort_values("period_start")
            colour = cmap(0.08 + 0.78 * i / max(1, len(vintages) - 1))
            ax.plot(sub.period_start, sub.projected, marker="o", markersize=3,
                    linewidth=1.3, color=colour, zorder=2,
                    label=f"WPP {int(v)}" if loc == 903 else None)
        actual = s.drop_duplicates("period_start").sort_values("period_start")
        ax.plot(actual.period_start, actual.actual, color=ACTUAL, linewidth=2.6, zorder=3,
                label="what happened" if loc == 903 else None)
        lo, hi = ax.get_ylim()
        if lo < 2.1 < hi:
            ax.axhline(2.1, color=MUTED, linewidth=0.9, linestyle=(0, (4, 3)), zorder=1)
            ax.annotate("replacement", xy=(0.99, 2.1), xycoords=("axes fraction", "data"),
                        xytext=(0, 4), textcoords="offset points",
                        ha="right", color=MUTED, fontsize=8)
        ax.set_title(f"{name}\n{subtitle}", color=INK, fontsize=11, loc="left", pad=10)
        ax.set_xlabel("five-year period beginning", color=MUTED, fontsize=9.5)
    axes[0].set_ylabel("children per woman", color=MUTED, fontsize=9.5)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=MUTED, ncol=2, loc="upper right")
    fig.suptitle("The two fertility mistakes that drove the population misses",
                 color=INK, fontsize=13, x=0.008, ha="left", y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.93))

    out = DOCS / "backtest-fertility.svg"
    fig.savefig(out, format="svg", transparent=True)
    plt.close(fig)
    _make_theme_aware(out)
    return out


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    pop_csv = paths.OUT / "backtest_population.csv"
    tfr_csv = paths.OUT / "backtest_tfr.csv"
    if not pop_csv.exists() or not tfr_csv.exists():
        raise SystemExit("Run scripts/run_backtest.py first.")

    a = world_population_figure(pd.read_csv(pop_csv))
    b = fertility_figure(pd.read_csv(tfr_csv))
    for p in (a, b):
        print(f"Wrote {p.relative_to(paths.REPO_ROOT)} ({p.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Draw a plain-language map of the projection model and its UN-style baseline.

The comparison is deliberately conceptual.  Both sides use the same demographic
bookkeeping; the difference is whether future fertility arrives as a projected
rate path or is partly generated from an explicit environment-and-composition
mechanism.

    python scripts/plot_model_flow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402


INK = "#252523"
MUTED = "#62605A"
LINE = "#BDB9AE"
SHARED = "#F1EFE8"
BLUE = "#E7F0F8"
BLUE_LINE = "#185FA5"
GREEN = "#E4F2ED"
GREEN_LINE = "#0F6E56"
PURPLE = "#EEE8F3"
PURPLE_LINE = "#762A83"


def box(ax, x, y, width, height, text, *, fill, edge, size=12.2,
        weight="normal", align="center", pad=18):
    """Add one rounded text box in diagram coordinates."""
    patch = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.012,rounding_size=14",
        linewidth=1.4, edgecolor=edge, facecolor=fill,
    )
    ax.add_patch(patch)
    tx = x + width / 2 if align == "center" else x + pad
    ax.text(
        tx, y + height / 2, text,
        ha=align, va="center", color=INK, fontsize=size,
        fontweight=weight, linespacing=1.5,
    )
    return patch


def arrow(ax, start, end, *, colour=LINE, connection="arc3"):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=14,
        linewidth=1.6, color=colour, connectionstyle=connection,
        shrinkA=3, shrinkB=3,
    ))


def main() -> int:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "svg.fonttype": "none",
    })
    fig, ax = plt.subplots(figsize=(12, 8.1))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 1200)
    ax.set_ylim(-18, 810)
    ax.axis("off")

    ax.text(
        600, 778, "How this population model works",
        ha="center", va="center", fontsize=21, fontweight="bold", color=INK,
    )
    ax.text(
        600, 748,
        "The demographic bookkeeping is shared. The theory of future fertility is not.",
        ha="center", va="center", fontsize=12.5, color=MUTED,
    )

    box(
        ax, 70, 632, 1060, 84,
        "STARTING EVIDENCE USED BY BOTH\n"
        "2024 population by country, age and sex  •  fertility by age  •  survival by age\n"
        "migration by age and sex  •  sex ratio at birth",
        fill=SHARED, edge=LINE, size=10.9, weight="bold",
    )

    ax.text(300, 594, "UN-STYLE BASELINE USED HERE", ha="center", va="center",
            fontsize=13.3, fontweight="bold", color=BLUE_LINE)
    ax.text(900, 594, "THIS PROJECT'S MECHANISM MODEL", ha="center", va="center",
            fontsize=13.3, fontweight="bold", color=GREEN_LINE)

    box(
        ax, 55, 460, 490, 104,
        "FUTURE RATE PATHS\n"
        "Fertility, survival and migration are\n"
        "statistically projected.\n"
        "Post-transition fertility tends to move back\n"
        "toward a long-run level.",
        fill=BLUE, edge=BLUE_LINE, size=9.4,
    )
    box(
        ax, 655, 438, 490, 126,
        "RATE PATHS + FERTILITY MECHANISM\n"
        "fertility environment  ×  family-size mix\n"
        "family-size spread + parent–child persistence\n"
        "named-group fertility + retention + convergence\n"
        "unresolved future choices stay explicit as scenarios",
        fill=GREEN, edge=GREEN_LINE, size=9.4,
    )

    box(
        ax, 55, 304, 490, 112,
        "YEARLY DEMOGRAPHIC LEDGER\n"
        "1  Age everyone   •   2  Apply survival\n"
        "3  Add births      •   4  Add migration",
        fill="white", edge=BLUE_LINE, size=12.0,
    )
    box(
        ax, 655, 304, 490, 112,
        "MECHANISM CHANGES BIRTHS FIRST\n"
        "environment × population mix\n"
        "→  realized fertility\n"
        "then use the same yearly demographic ledger",
        fill="white", edge=GREEN_LINE, size=10.8,
    )

    box(
        ax, 55, 150, 490, 112,
        "OUTPUTS\n"
        "Population by country, age and sex\n"
        "through 2150\n"
        "+ a conventional UW-posterior uncertainty band",
        fill=BLUE, edge=BLUE_LINE, size=9.8,
    )
    box(
        ax, 655, 136, 490, 126,
        "OUTPUTS\n"
        "The same population paths, plus\n"
        "population composition and selection effect,\n"
        "whether and when fertility rebounds,\n"
        "scenario ranges and an uncertainty breakdown",
        fill=PURPLE, edge=PURPLE_LINE, size=9.4,
    )

    arrow(ax, (300, 456), (300, 420), colour=BLUE_LINE)
    arrow(ax, (900, 434), (900, 420), colour=GREEN_LINE)
    arrow(ax, (300, 300), (300, 266), colour=BLUE_LINE)
    arrow(ax, (900, 300), (900, 266), colour=PURPLE_LINE)

    ax.plot([600, 600], [136, 564], color=LINE, lw=1.0)
    box(
        ax, 145, 32, 910, 90,
        "UN-style question:  If these future rates occur, how many people follow?\n"
        "This project's extra question:\n"
        "How do the rates change when the environment and the population mix change?",
        fill=SHARED, edge=LINE, size=10.6,
    )
    ax.text(
        600, 14,
        "Conceptual map, not every source-file or fitting step. Official WPP projections end in 2100; "
        "this repo holds 2100 rates constant to reach 2150.",
        ha="center", va="center", fontsize=8.8, color=MUTED,
    )

    paths.OUT.mkdir(parents=True, exist_ok=True)
    (paths.REPO_ROOT / "docs").mkdir(parents=True, exist_ok=True)
    svg = paths.REPO_ROOT / "docs" / "how-the-model-works.svg"
    png = paths.OUT / "model-flow.png"
    fig.savefig(svg, format="svg", bbox_inches="tight", facecolor="white")
    fig.savefig(png, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Matplotlib's SVG is visual-only by default.  Give the committed diagram a
    # useful name and description for screen readers; build_map.py preserves
    # these attributes when it embeds the figure in the page.
    markup = svg.read_text(encoding="utf-8")
    svg_at = markup.index("<svg")
    tag_end = markup.index(">", svg_at)
    tag = markup[svg_at:tag_end]
    tag += ' role="img" aria-labelledby="model-flow-title model-flow-desc"'
    accessible = (
        '<title id="model-flow-title">How this population model works</title>'
        '<desc id="model-flow-desc">Both models start with population, fertility, '
        'survival, migration, and sex-ratio data. The UN-style baseline projects '
        'future rate paths and passes them through a demographic ledger. This project '
        'also models how fertility environment and population composition interact, '
        'then reports population, composition, selection, rebound, scenario, and '
        'uncertainty outputs.</desc>'
    )
    markup = markup[:svg_at] + tag + markup[tag_end:tag_end + 1] + accessible + markup[tag_end + 1:]
    markup = "\n".join(line.rstrip() for line in markup.splitlines()) + "\n"
    svg.write_text(markup, encoding="utf-8")
    print(f"wrote {svg}")
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

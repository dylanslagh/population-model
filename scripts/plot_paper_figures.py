"""Draw the paper's figures from committed result files.

These are deliberately separate from the review figures in `docs/`. A review
figure carries its own title and caveat because it is looked at on its own; a
paper figure does not, because the caption beside it does that job and a
duplicated title reads as clutter. Everything here is vector PDF for the
manuscript plus a PNG at the same size, because the only reliable way to catch
a figure that is wrong is to open the PNG and look at it.

    python scripts/plot_paper_figures.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from popmodel.mech import composition  # noqa: E402

FIGURES = REPO / "paper" / "figures"
REVIEW = REPO / "out" / "paper-figures"

# One restrained palette for the whole manuscript, so a colour means the same
# thing in every figure: blue is the environment alone, orange is selection,
# red is the stress test, grey is somebody else's number.
ENVIRONMENT = "#2C6FAF"
SELECTION = "#D97706"
PRESSURE = "#B83B5E"
NEUTRAL = "#555555"
LIGHT = "#BBBBBB"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "font.size": 8.5,
    "axes.labelsize": 8.5,
    "axes.titlesize": 9,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,  # or the gridlines stripe every bar
    "grid.color": "#E3E3E3",
    "grid.linewidth": 0.6,
    "figure.dpi": 110,
})


def load(relative: str) -> dict:
    path = REPO / relative
    if not path.exists():
        raise SystemExit(f"{relative} is missing; regenerate it before plotting")
    return json.loads(path.read_text(encoding="utf-8"))


def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(REVIEW / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  paper/figures/{name}.pdf  and  out/paper-figures/{name}.png")


def panel_letter(ax, letter: str) -> None:
    ax.set_title(letter, loc="left", fontweight="bold", fontsize=9.5, pad=6)


# --------------------------------------------------------------------------
# Figure 1: what the mechanism is
# --------------------------------------------------------------------------

def figure_mechanism(phase5: dict) -> None:
    cv = 0.57
    persistence = 0.15
    bins = composition.propensity_bins(3, cv)

    fig, axes = plt.subplots(1, 3, figsize=(6.9, 2.35), layout="constrained")

    # (a) the distribution the three types stand in for.
    ax = axes[0]
    sigma = math.sqrt(math.log1p(cv * cv))
    mu = -0.5 * sigma * sigma  # so the mean is exactly one
    x = np.linspace(0.01, 3.2, 600)
    density = np.exp(-((np.log(x) - mu) ** 2) / (2 * sigma ** 2)) / (
        x * sigma * math.sqrt(2 * math.pi)
    )
    ax.fill_between(x, density, color=SELECTION, alpha=0.16, lw=0)
    ax.plot(x, density, color=SELECTION, lw=1.4)
    top = density.max()
    for value, label, height in zip(bins, ("low", "middle", "high"),
                                    (0.42, 0.62, 0.82)):
        ax.axvline(value, color=NEUTRAL, lw=0.9, ls=(0, (3, 2)))
        ax.annotate(f"{label}\n{value:.2f}", (value, top * height),
                    xytext=(4, 0), textcoords="offset points",
                    fontsize=7.2, color="#333333", ha="left", va="center")
    ax.set(xlabel="relative completed family size",
           ylabel="density", xlim=(0, 3.2), ylim=(0, top * 1.08))
    ax.set_yticks([])
    panel_letter(ax, "a")

    # (b) the composition actually drifting.
    ax = axes[1]
    race = phase5["scenarios"]["race"]
    years = np.array(race["years"])
    path = race["world_composition_path"]
    labels = ["mainstream-low", "mainstream-middle", "mainstream-high"]
    stack = np.array([path[label] for label in labels]) * 100
    ax.stackplot(years, stack,
                 colors=["#CFE0F0", "#8FB6DA", SELECTION],
                 edgecolor="white", linewidth=0.3)
    ax.grid(visible=False)
    ax.set(xlabel="year", ylabel="share of world population (%)",
           xlim=(years[0], years[-1]), ylim=(0, 100))
    for label, y, text in (
        ("low", 12, "low"), ("middle", 42, "middle"), ("high", 82, "high"),
    ):
        ax.text(years[-1] - 3, y, text, fontsize=7.4, ha="right",
                color="#1F3B57" if text != "high" else "white")
    panel_letter(ax, "b")

    # (c) what that does to fertility, with the mechanism's own uncertainty.
    ax = axes[2]
    rate_years = years[:-1]
    ensemble = phase5["ensemble"]["race"]["effect_band"]
    ax.fill_between(rate_years, ensemble["p05"], ensemble["p95"],
                    color=SELECTION, alpha=0.16, lw=0,
                    label=f"{phase5['ensemble']['draws']} parameter draws")
    ax.plot(rate_years, race["selection_effect_path"], color=SELECTION, lw=1.8,
            label="central setting")
    ax.axhline(1.0, color=NEUTRAL, lw=0.9)
    ax.set(xlabel="year", ylabel="observed fertility / environment alone",
           xlim=(years[0], years[-1]))
    ax.legend(frameon=False, loc="upper left", handlelength=1.4)
    panel_letter(ax, "c")

    save(fig, "fig1-mechanism")


# --------------------------------------------------------------------------
# Figure 2: the attribution ladder
# --------------------------------------------------------------------------

def figure_ladder(sensitivity: dict) -> None:
    ladder = sensitivity["model_ladder"]
    labels = [
        "Stable-low environment,\nno selection",
        "+ measured mainstream\nselection",
        "+ named high-fertility\ngroups",
        "+ 4% per decade extra\nenvironmental decline",
    ]
    values = [row["world_2150_billions"] for row in ladder]
    basis_color = [NEUTRAL, SELECTION, SELECTION, PRESSURE]

    fig, ax = plt.subplots(figsize=(6.0, 2.6), layout="constrained")
    positions = np.arange(len(values))

    # A waterfall: each bar starts where the last one ended, so the height of
    # the coloured segment is the size of that step's claim.
    ax.bar(positions[0], values[0], width=0.62, color=NEUTRAL, alpha=0.55)
    for index in range(1, len(values)):
        low = min(values[index - 1], values[index])
        height = abs(values[index] - values[index - 1])
        ax.bar(positions[index], height, bottom=low, width=0.62,
               color=basis_color[index], alpha=0.85)
        ax.plot([positions[index - 1] - 0.31, positions[index] + 0.31],
                [values[index - 1]] * 2, color="#999999", lw=0.8, ls=(0, (2, 2)))
    for index, value in enumerate(values):
        delta = "" if index == 0 else f"\n({value - values[index - 1]:+.2f})"
        ax.text(positions[index], max(values[index], values[max(index - 1, 0)]) + 0.18,
                f"{value:.2f}{delta}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=7.6)
    ax.set_ylabel("world population in 2150 (billions)")
    ax.set_ylim(0, max(values) + 1.6)
    ax.grid(axis="x", visible=False)
    save(fig, "fig2-ladder")


# --------------------------------------------------------------------------
# Figure 3: the boundary
# --------------------------------------------------------------------------

def figure_boundary(paired: dict) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 3.3), layout="constrained")
    colors = {0.44: ENVIRONMENT, 0.57: SELECTION, 0.80: PRESSURE}
    for cv in paired["parameter_grid"]["cv_values"]:
        rows = [r for r in paired["rows"]
                if abs(r["mainstream_propensity_cv"] - cv) < 1e-12]
        x = np.array([r["mainstream_persistence"] for r in rows])
        band = [r["break_even_decline_per_decade"] for r in rows]
        lo = 100 * np.array([b["p05"] for b in band])
        mid = 100 * np.array([b["p50"] for b in band])
        hi = 100 * np.array([b["p95"] for b in band])
        color = colors[round(cv, 2)]
        ax.fill_between(x, lo, hi, color=color, alpha=0.20, lw=0)
        ax.plot(x, mid, color=color, lw=2.0,
                label=f"family-size CV {cv:.2f}")

    central = paired["central_result"]
    cx = central["mainstream_persistence"]
    cy = 100 * central["break_even_decline_per_decade"]["p50"]
    ax.scatter([cx], [cy], color="#111111", zorder=5, s=22)
    ax.annotate(f"measured setting:\n{cy:.2f}% per decade",
                (cx, cy), xytext=(cx + 0.025, cy - 0.85), fontsize=7.8,
                arrowprops={"arrowstyle": "-", "color": "#444444", "lw": 0.8})
    ax.axhline(4, color=NEUTRAL, lw=1.0, ls=(0, (4, 3)))
    ax.text(0.296, 4.08, "illustrative 4% stress test", fontsize=7.6,
            color=NEUTRAL, ha="right")
    ax.set(xlim=(0.045, 0.305), ylim=(0, 4.9),
           xlabel="parent–child persistence in family size",
           ylabel="additional universal decline\nthat cancels selection (% per decade)")
    ax.legend(frameon=False, loc="upper left", handlelength=1.6)
    save(fig, "fig3-boundary")


# --------------------------------------------------------------------------
# Figure 4: the three objects and the 2100 boundary
# --------------------------------------------------------------------------

def figure_boundary_2100(phase5: dict) -> None:
    """The three separate objects, and where each one stops being the UN's.

    The extension is drawn from the stored annual draws rather than from the
    three dates in the summary receipt: joining 2100, 2125 and 2150 with
    straight lines would show a path shape the model never produced.
    """
    totals = np.load(REPO / "out" / "un_project_extension_country_totals.npz",
                     allow_pickle=True)
    fig, ax = plt.subplots(figsize=(6.3, 3.4), layout="constrained")
    scenarios = phase5["scenarios"]
    years = np.array(scenarios["un-equivalent"]["years"])

    official_years = totals["official_years"]
    ax.plot(official_years, totals["official_world"] / 1e9, color=NEUTRAL,
            lw=2.0, label="UN reproduction (WPP 2024 medium, to 2100)")

    extension_years = totals["extension_years"]
    world = totals["world"] / 1e9
    ax.fill_between(extension_years,
                    np.quantile(world, 0.05, axis=0),
                    np.quantile(world, 0.95, axis=0),
                    color=NEUTRAL, alpha=0.25, lw=0)
    ax.plot(extension_years, np.quantile(world, 0.50, axis=0), color=NEUTRAL,
            lw=1.6, ls=(0, (5, 2)),
            label="UN project extension (migration only)")

    ax.plot(years, scenarios["stable-low"]["world_path_billions"],
            color=SELECTION, lw=2.0, label="selection model, no extra pressure")
    ax.plot(years, scenarios["race"]["world_path_billions"],
            color=PRESSURE, lw=2.0, label="selection model, 4% stress test")

    # The labels sit along the bottom rather than beside the rules: at the top
    # the 2100 rule crosses the selection curves and the text lands on them.
    for year, text in ((2024, "2024: the selection model forks"),
                       (2100, "2100: the UN's assumptions stop")):
        ax.axvline(year, color="#333333", lw=0.9, ls=(0, (1, 2)))
        ax.text(year + 2, 6.92, text, fontsize=7.4, color="#333333",
                va="bottom", ha="left")

    ax.set(xlabel="year", ylabel="world population (billions)",
           xlim=(years[0], years[-1]), ylim=(6.8, 11.5))
    ax.legend(frameon=False, loc="upper left", handlelength=1.8)
    save(fig, "fig4-boundary-2100")


# --------------------------------------------------------------------------
# Figure 5: which uncertainty dominates, and where
# --------------------------------------------------------------------------

def figure_decomposition(decomposition: dict) -> None:
    sources = decomposition["sources"]
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.7), layout="constrained",
                             gridspec_kw={"width_ratios": [1.05, 1]})

    ax = axes[0]
    entries = [
        ("long-run fertility", sources["fertility"]["world_width_billions"]["2150"],
         ENVIRONMENT),
        ("the selection mechanism", decomposition["mechanism"]["2150"], SELECTION),
        ("our own post-2100 rule",
         sources["stop-at-2090"]["world_width_billions"]["2150"]
         - sources["everything"]["world_width_billions"]["2150"], NEUTRAL),
        ("mortality", sources["mortality"]["world_width_billions"]["2150"], LIGHT),
        ("migration", sources["migration"]["world_width_billions"]["2150"], LIGHT),
    ]
    names = [e[0] for e in entries]
    values = [e[1] for e in entries]
    ax.barh(np.arange(len(entries)), values,
            color=[e[2] for e in entries], height=0.62)
    for index, value in enumerate(values):
        ax.text(value + 0.12, index, f"{value:.2f}", va="center", fontsize=7.8)
    ax.set_yticks(np.arange(len(entries)))
    ax.set_yticklabels(names, fontsize=7.8)
    ax.invert_yaxis()
    ax.set_xlabel("90% width of world population in 2150 (billions)")
    ax.set_xlim(0, max(values) * 1.22)
    ax.grid(axis="y", visible=False)
    panel_letter(ax, "a")

    # A bar's length carries no meaning on a log axis, so this panel is drawn
    # as a deviation from parity: the dot is the ratio, the stem runs back to
    # one, and which side of one it falls on is the whole point.
    ax = axes[1]
    fertility = sources["fertility"]["countries_2100_width_millions"]
    migration = sources["migration"]["countries_2100_width_millions"]
    names = {"ARE": "United Arab Emirates", "CAN": "Canada",
             "USA": "United States", "JPN": "Japan", "PHL": "Philippines",
             "NGA": "Nigeria"}
    ratios = {iso3: migration[iso3] / fertility[iso3] for iso3 in names}
    order = sorted(ratios, key=ratios.get, reverse=True)
    for index, iso3 in enumerate(order):
        value = ratios[iso3]
        color = SELECTION if value > 1 else ENVIRONMENT
        ax.plot([1.0, value], [index, index], color=color, lw=1.4, zorder=2)
        ax.scatter([value], [index], color=color, s=26, zorder=3)
        # Always to the right of the dot: a label placed leftward on the low
        # side runs straight into the country name.
        ax.annotate(f"{value:.2f}×", (value, index), xytext=(9, 0),
                    textcoords="offset points", fontsize=7.8, va="center",
                    ha="left")
    ax.axvline(1.0, color="#333333", lw=0.9, zorder=1)
    ax.set_xscale("log")
    ax.set_yticks(np.arange(len(order)))
    ax.set_yticklabels([names[iso3] for iso3 in order], fontsize=7.8)
    ax.set_ylim(len(order) - 0.5, -0.5)
    ax.set_xlabel("migration ÷ fertility uncertainty, 2100")
    ax.set_xlim(0.02, 300)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(axis="y", visible=False)
    panel_letter(ax, "b")

    save(fig, "fig5-decomposition")


def main() -> int:
    phase5 = load("out/phase5.json")
    if "ensemble" not in phase5:
        raise SystemExit(
            "out/phase5.json has no parameter ensemble; rerun "
            "scripts/run_phase5.py --ensemble 200"
        )
    if "world_composition_path" not in phase5["scenarios"]["race"]:
        raise SystemExit(
            "out/phase5.json predates the composition path; rerun run_phase5.py"
        )
    print("writing paper figures")
    figure_mechanism(phase5)
    figure_ladder(load("data/reference/selection_break_even_sensitivity.json"))
    figure_boundary(load("data/reference/paired_selection_boundary_sensitivity.json"))
    figure_boundary_2100(phase5)
    figure_decomposition(load("out/uncertainty_decomposition.json"))
    print("open every PNG in out/paper-figures/ before trusting the PDFs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

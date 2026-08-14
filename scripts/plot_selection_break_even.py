"""Plot the selection-first break-even analysis and model-reduction ladder.

    python scripts/plot_selection_break_even.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.mech import sensitivity  # noqa: E402


DATA = paths.REFERENCE / "selection_break_even_sensitivity.json"
SVG = paths.REPO_ROOT / "docs" / "selection-break-even.svg"
PNG = paths.OUT / "selection-break-even.png"


def main() -> int:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    rows = payload["rows"]
    persistence = np.array(payload["persistence_values"], dtype=float)
    cv_values = np.array(payload["cv_values"], dtype=float)
    rates = np.linspace(*payload["pressure_range_per_decade"], 161)
    final_year = int(rows[0]["final_rate_year"])
    decades = (final_year - int(payload["pressure_from"])) / 10.0

    effect_by_cv = {}
    boundary_by_cv = {}
    for cv in cv_values:
        selected = sorted(
            (row for row in rows if abs(row["mainstream_propensity_cv"] - cv) < 1e-10),
            key=lambda row: row["mainstream_persistence"],
        )
        effect_by_cv[cv] = np.array(
            [row["selection_effect_final"] for row in selected], dtype=float
        )
        boundary_by_cv[cv] = np.array(
            [row["break_even_decline_per_decade"] for row in selected], dtype=float
        )

    central_cv = 0.57
    net = sensitivity.net_fertility_multiplier(
        effect_by_cv[central_cv][:, None], rates[None, :], decades
    )

    plt.rcParams.update({"svg.fonttype": "none", "font.family": "DejaVu Sans"})
    fig, (ax, ladder_ax) = plt.subplots(
        1, 2, figsize=(12.8, 5.7), gridspec_kw={"width_ratios": [1.2, 0.8]}
    )
    colours = ["#F4DFD8", "#F7F5EF", "#D9EFE5"]
    cmap = LinearSegmentedColormap.from_list("pressure-balance", colours)
    norm = TwoSlopeNorm(vmin=float(net.min()), vcenter=1.0, vmax=float(net.max()))
    # Rasterise only the smooth colour field. Gouraud-shaded SVG polygons turn
    # this tiny heatmap into ten megabytes; labels, boundary and points remain
    # vector and the committed figure stays small enough to inline on the page.
    mesh = ax.imshow(
        net,
        origin="lower",
        extent=(100 * rates.min(), 100 * rates.max(), persistence.min(), persistence.max()),
        aspect="auto",
        interpolation="bilinear",
        cmap=cmap,
        norm=norm,
    )
    low, center, high = cv_values
    ax.fill_betweenx(
        persistence,
        100 * boundary_by_cv[low],
        100 * boundary_by_cv[high],
        color="#185FA5", alpha=0.13, lw=0,
        label="observed family-size spread, country range",
    )
    ax.plot(
        100 * boundary_by_cv[center], persistence,
        color="#185FA5", lw=2.1, label="median observed spread (0.57)",
    )
    central_row = next(
        row for row in rows
        if abs(row["mainstream_propensity_cv"] - center) < 1e-10
        and abs(row["mainstream_persistence"] - 0.15) < 1e-10
    )
    central_boundary = 100 * central_row["break_even_decline_per_decade"]
    ax.scatter([central_boundary], [0.15], s=38, color="#185FA5", zorder=4)
    ax.annotate(
        f"central evidence: {central_boundary:.2f}%",
        (central_boundary, 0.15), xytext=(10, 12), textcoords="offset points",
        fontsize=8.5, color="#185FA5",
    )
    ax.scatter([4.0], [0.15], s=46, marker="x", linewidth=2, color="#993C1D", zorder=4)
    ax.annotate(
        "4% stress test", (4.0, 0.15), xytext=(-8, -18),
        textcoords="offset points", ha="right", fontsize=8.5, color="#993C1D",
    )
    ax.text(0.25, 0.287, "selection outweighs\nadded pressure", ha="left", va="top",
            fontsize=9, color="#0F6E56")
    ax.text(3.78, 0.287, "added pressure\noutweighs selection", ha="right", va="top",
            fontsize=9, color="#993C1D")
    ax.set_xlim(0, 4.15)
    ax.set_ylim(persistence.min(), persistence.max())
    ax.set_xlabel("additional fertility-environment decline per decade after 2050")
    ax.set_ylabel("parent–child persistence in completed family size")
    ax.set_title("Where mainstream selection breaks even by 2150", fontsize=11)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, fraction=0.05)
    cbar.set_label("net fertility multiplier", fontsize=8.5)
    cbar.ax.tick_params(labelsize=8)

    ladder = payload["model_ladder"]
    y = np.arange(len(ladder))[::-1]
    values = np.array([row["world_2150_billions"] for row in ladder])
    ladder_colours = ["#77756F", "#0F6E56", "#0F6E56", "#993C1D"]
    ladder_ax.hlines(y, values.min() - 0.35, values, color="#D3D1C7", lw=1.2)
    ladder_ax.scatter(values, y, s=62, color=ladder_colours, zorder=3)
    for index, (row, value, ypos) in enumerate(zip(ladder, values, y)):
        ladder_ax.text(value + 0.09, ypos, f"{value:.2f}bn", va="center", fontsize=9.2)
        if index:
            delta = row["change_from_previous_billions"]
            ladder_ax.text(
                values.min() - 0.30, ypos + 0.24, f"change: {delta:+.2f}bn",
                va="center", fontsize=7.8, color="#62605A",
            )
    ladder_ax.set_yticks(y, [row["label"] for row in ladder], fontsize=8.6)
    ladder_ax.set_xlim(values.min() - 0.45, values.max() + 0.75)
    ladder_ax.set_xlabel("world population in 2150, billions")
    ladder_ax.set_title("Which added assumption moves the answer?", fontsize=11)
    ladder_ax.spines[["top", "right", "left"]].set_visible(False)
    ladder_ax.tick_params(axis="y", length=0)
    ladder_ax.grid(axis="x", color="#E1DFD7", lw=0.8)

    fig.suptitle(
        "Selection first; future development pressure as a stress test",
        fontsize=12.3,
    )
    fig.text(
        0.5, 0.015,
        "Left: additional pressure is measured relative to the stable-low path; "
        "the blue boundary is net fertility = 1.  Right: the 4% path is an "
        "illustrative knob, not an economic forecast.",
        ha="center", fontsize=8.0, color="#62605A",
    )
    fig.tight_layout(rect=(0, 0.055, 1, 0.94))
    paths.OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(SVG, format="svg", facecolor="white")
    fig.savefig(PNG, format="png", dpi=170, facecolor="white")
    plt.close(fig)

    markup = SVG.read_text(encoding="utf-8")
    svg_at = markup.index("<svg")
    tag_end = markup.index(">", svg_at)
    tag = markup[svg_at:tag_end]
    tag += ' role="img" aria-labelledby="selection-boundary-title selection-boundary-desc"'
    accessible = (
        '<title id="selection-boundary-title">Selection and development-pressure break-even</title>'
        '<desc id="selection-boundary-desc">A sensitivity map shows the additional '
        'post-2050 environmental decline needed to cancel mainstream fertility '
        'selection by 2150. A model ladder shows that measured mainstream selection '
        'and named groups raise the stable-low projection, while the illustrative '
        'four-percent development-pressure scenario lowers it substantially.</desc>'
    )
    markup = markup[:svg_at] + tag + markup[tag_end:tag_end + 1] + accessible + markup[tag_end + 1:]
    markup = "\n".join(line.rstrip() for line in markup.splitlines()) + "\n"
    SVG.write_text(markup, encoding="utf-8")
    print(f"wrote {SVG}")
    print(f"wrote {PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

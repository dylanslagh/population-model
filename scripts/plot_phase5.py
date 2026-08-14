"""Draw the race: does selection catch the moving environmental target?

Two panels.

**Left, the four corners.** World population under each combination of the two
axes. The gap between the top and bottom pair is what selection does; the gap
between the left and right pair is what continued development pressure does.
Both are drawn against the same UN-equivalent baseline, so the comparison is
between mechanisms and not between implementations.

**Right, the answer.** Observed fertility divided by what the environment alone
would have produced, world-wide, weighted by births. Above one means the
composition of the population has pushed fertility above the environment path.
The band is what the mechanism's own parameter ranges imply, and it is wide
because those ranges are wide.

Read the caveat on the figure. All eight sourced parameters have been checked,
but five scenario knobs remain unresolved. The shape of these curves is a claim
about a mechanism; their height is conditional on those assumptions.

    python scripts/plot_phase5.py
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

CORNERS = (
    ("un-equivalent", "#4575b4", "solid", "UN environment, no selection"),
    ("full-selection-un-environment", "#1a9850", (0, (6, 2)),
     "UN environment, full selection"),
    ("development-pressure", "#d73027", (0, (1, 1)), "Continued pressure, no selection"),
    ("race", "#762a83", (0, (4, 1, 1, 1)), "Continued pressure, full selection"),
)


def main() -> int:
    payload = json.loads((paths.OUT / "phase5.json").read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]

    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.4))

    ax = axes[0]
    for key, colour, dashes, label in CORNERS:
        run = scenarios[key]
        ax.plot(run["years"], run["world_path_billions"], color=colour, ls=dashes,
                lw=1.9, label=label)
    ax.set_xlim(2024, 2150)
    ax.set_ylim(0, None)
    ax.set_xlabel("year")
    ax.set_ylabel("world population, billions")
    ax.set_title("The four corners of the two-axis grid", fontsize=10.5)
    ax.legend(fontsize=7.8, frameon=False, loc="lower left")
    ax.spines[["top", "right"]].set_visible(False)

    ax = axes[1]
    ensemble = payload.get("ensemble", {}).get("race")
    if ensemble:
        years = scenarios["race"]["years"][: len(ensemble["effect_band"]["p50"])]
        ax.fill_between(
            years, ensemble["effect_band"]["p05"], ensemble["effect_band"]["p95"],
            color="#762a83", alpha=0.16, lw=0,
            label=f"race: {payload['ensemble']['draws']} parameter draws",
        )
    for key, colour, dashes, label in CORNERS:
        run = scenarios[key]
        effect = run["selection_effect_path"]
        ax.plot(run["years"][: len(effect)], effect, color=colour, ls=dashes, lw=1.7,
                label=label)
    anchored = scenarios.get("race-anchored-culture")
    if anchored:
        effect = anchored["selection_effect_path"]
        ax.plot(anchored["years"][: len(effect)], effect, color="#762a83", lw=1.2,
                alpha=0.65, ls=(0, (2, 2)),
                label="race, culture anchored to 2024 instead")
    ax.axhline(1.0, color="0.4", lw=1)
    ax.set_xlim(2024, 2150)
    ax.set_xlabel("year")
    ax.set_ylabel("observed fertility / environment alone")
    ax.set_title("Does selection overtake the environment?", fontsize=10.5)
    # The two full-selection curves sit exactly on top of each other, and that
    # is a property of the model rather than a plotting mistake: the
    # environment multiplies every type equally, so it cancels out of the
    # relative birth weights that drive composition. Selection's proportional
    # effect is therefore the same under either environment. Saying so on the
    # figure is better than letting a reader think one line is missing.
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle(
        "Phase 5: selection against a changing fertility environment", fontsize=11.5
    )
    fig.text(
        0.5, 0.058,
        chr(10).join([
            "The two full-selection curves coincide on the right. That is the "
            "model, not the plot: the environment multiplies every type equally,",
            "so it cancels out of who has children relative to whom. Selection "
            "and environment are separable here, which is itself an assumption "
            "worth doubting.",
        ]),
        ha="center", fontsize=7.4, color="0.4", linespacing=1.7,
    )
    fig.text(
        0.5, 0.012,
        "Conditional magnitudes: 8 of 13 parameters verified against sources; "
        "5 are scenario knobs with no independently established future value.",
        ha="center", fontsize=7.4, color="0.35",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))

    paths.OUT.mkdir(parents=True, exist_ok=True)
    png = paths.OUT / "phase5.png"
    fig.savefig(png, dpi=150)
    fig.savefig(paths.REPO_ROOT / "docs" / "phase5.svg")
    plt.close(fig)
    print(f"wrote {png}")
    print(f"wrote {paths.REPO_ROOT / 'docs' / 'phase5.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

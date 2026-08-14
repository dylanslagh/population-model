"""What the uncertainty is made of, at two different scales.

The band says the answer is uncertain. This says what about. Each bar is the
width of the 90% range when one source is varied across its own draws and
everything else is held at a median trajectory.

The point of putting the world and the countries side by side is that they
disagree. For the world, migration barely matters -- it has to cancel, one
person leaves and one arrives. For the United Arab Emirates it is almost the
whole answer. A page that shows only one of those is telling half the truth.

    python scripts/plot_decomposition.py
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

# "everything" varies fertility and mortality together; migration stays at its
# median there, because the published run has only one migration path. Saying
# so in the label is the difference between a chart and a claim.
LABELS = {
    "fertility": "fertility",
    "migration": "migration",
    "mortality": "mortality",
    "everything": "fertility and\nmortality together",
    "stop-at-2090": "ten fewer years of\nsource data: the cost\nof our own rule",
}
ORDER = ("fertility", "migration", "mortality", "everything", "stop-at-2090")
COLOUR = {
    "fertility": "#4575b4", "migration": "#1a9850", "mortality": "#8c8c8c",
    "everything": "#2c4f7c", "stop-at-2090": "#d99100",
}
COUNTRIES = ("ARE", "CAN", "JPN", "USA", "PHL", "NGA")


def main() -> int:
    payload = json.loads(
        (paths.OUT / "uncertainty_decomposition.json").read_text(encoding="utf-8")
    )
    sources = payload["sources"]
    mechanism = payload.get("mechanism")

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.0))

    ax = axes[0]
    keys = [k for k in ORDER if k in sources]
    # The hold-constant rule is reported as what it ADDS, not as a total. The
    # total would sit beside the others looking like a sixth independent
    # source, when it is the same run with ten fewer years of evidence.
    def world_width(key):
        value = sources[key]["world_width_billions"]["2150"]
        if key == "stop-at-2090":
            return value - sources["everything"]["world_width_billions"]["2150"]
        return value

    widths = [world_width(k) for k in keys]
    labels = [LABELS[k] for k in keys]
    colours = [COLOUR[k] for k in keys]
    if mechanism:
        keys.append("mechanism")
        widths.append(mechanism["2150"])
        labels.append("the mechanism\n(selection vs\nopportunity cost)")
        colours.append("#762a83")
    y = np.arange(len(keys))
    ax.barh(y, widths, color=colours, height=0.62)
    for i, w in enumerate(widths):
        ax.text(w + 0.12, i, f"{w:.2f}", va="center", fontsize=9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("width of the 90% range at 2150, billions of people")
    ax.set_xlim(0, max(widths) * 1.22)
    ax.set_title("World: what we do not know is fertility", fontsize=10.5)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)

    ax = axes[1]
    fert = [sources["fertility"]["countries_2100_width_millions"][c] for c in COUNTRIES]
    migr = [sources["migration"]["countries_2100_width_millions"][c] for c in COUNTRIES]
    y = np.arange(len(COUNTRIES))
    ax.barh(y - 0.19, fert, height=0.36, color=COLOUR["fertility"], label="fertility")
    ax.barh(y + 0.19, migr, height=0.36, color=COLOUR["migration"], label="migration")
    for i, (a, b) in enumerate(zip(fert, migr)):
        ratio = b / a if a > 0 else float("inf")
        note = f"{ratio:.2f}x" if ratio < 1 else f"{ratio:.1f}x"
        ax.text(max(a, b) * 1.12, i, note, va="center", fontsize=8.5, color="0.35")
    ax.set_yticks(y)
    ax.set_yticklabels(COUNTRIES, fontsize=9.5)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("width of the 90% range at 2100, millions (log scale)")
    ax.set_xlim(right=max(max(fert), max(migr)) * 2.2)
    ax.set_title(
        "Countries: migration relative to fertility", fontsize=10.5
    )
    ax.legend(fontsize=8.5, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.13), ncol=2)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)

    fig.suptitle(
        "Where the width of the band comes from", fontsize=12
    )
    fig.text(
        0.5, 0.035,
        chr(10).join([
            "One source varied across its own draws at a time, the others held at a "
            "median trajectory. The mechanism bar is not additive with the others:",
            "its demographic rates are the UN medium path; seven parameters are "
            "source-checked, five are knobs, and one sourced dispersion remains "
            "unverified. The published band contains no migration uncertainty.",
        ]),
        ha="center", fontsize=7.6, color="0.4", linespacing=1.7,
    )
    fig.tight_layout(rect=(0, 0.085, 1, 0.93))

    png = paths.OUT / "decomposition.png"
    fig.savefig(png, dpi=150)
    fig.savefig(paths.REPO_ROOT / "docs" / "decomposition.svg")
    plt.close(fig)

    print("world 90% width at 2150, billions:")
    for key in keys:
        w = mechanism["2150"] if key == "mechanism" else world_width(key)
        print(f"  {key:<14} {w:5.2f}")
    print("\nper country at 2100, millions of width:")
    for c in COUNTRIES:
        f = sources["fertility"]["countries_2100_width_millions"][c]
        m = sources["migration"]["countries_2100_width_millions"][c]
        print(f"  {c}  fertility {f:7.1f}   migration {m:7.1f}   migration is {m/f:5.1f}x")
    print(f"\nwrote {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

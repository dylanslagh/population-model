"""Plot the paired-migration robustness receipt for the selection boundary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402


def main() -> None:
    source = paths.REFERENCE / "paired_selection_boundary_sensitivity.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
    colors = {0.44: "#5B8FF9", 0.57: "#D97706", 0.80: "#B83B5E"}
    for cv in payload["parameter_grid"]["cv_values"]:
        rows = [r for r in payload["rows"] if abs(r["mainstream_propensity_cv"] - cv) < 1e-12]
        x = np.array([r["mainstream_persistence"] for r in rows])
        lo = 100 * np.array([r["break_even_decline_per_decade"]["p05"] for r in rows])
        mid = 100 * np.array([r["break_even_decline_per_decade"]["p50"] for r in rows])
        hi = 100 * np.array([r["break_even_decline_per_decade"]["p95"] for r in rows])
        color = colors[round(cv, 2)]
        ax.fill_between(x, lo, hi, color=color, alpha=.18)
        ax.plot(x, mid, color=color, lw=2.5, label=f"family-size CV {cv:.2f}")
    ax.axhline(4, color="#555555", lw=1.2, ls="--", label="4% stress-test path")
    ax.scatter([.15], [1.5226737671560131], color="#111111", zorder=5)
    ax.annotate("central measured setting\n1.52% per decade", (.15, 1.5227), xytext=(.18, .62),
                arrowprops={"arrowstyle": "-", "color": "#444"}, fontsize=9)
    ax.set(xlim=(.045, .305), ylim=(0, 4.8), xlabel="Parent–child persistence", ylabel="Additional universal decline (% per decade)")
    ax.set_title("How much shared downward pressure would cancel mainstream selection?")
    ax.text(.05, 4.58, "Bands: 5th–95th percentile across 50 paired migration paths", fontsize=9, color="#555555")
    ax.grid(axis="y", color="#d9d9d9", lw=.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="lower right")
    svg = paths.REPO_ROOT / "docs" / "selection-break-even-paired.svg"
    png = paths.OUT / "selection-break-even-paired.png"
    fig.savefig(svg, bbox_inches="tight")
    fig.savefig(png, dpi=180, bbox_inches="tight")
    print(f"wrote {svg.relative_to(paths.REPO_ROOT)}")
    print(f"wrote {png.relative_to(paths.REPO_ROOT)}")


if __name__ == "__main__":
    main()

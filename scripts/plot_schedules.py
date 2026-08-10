"""Draw what the schedule converter actually does to the UN's age patterns.

The numbers in `check_schedules.py` prove the converter reproduces its inputs.
They cannot show whether the schedules it invents along the way are shaped like
anything a demographer would recognise. That needs looking at.

Each row is one country in 2100. On the left, the fertility age pattern for the
median draw and for the 5th and 95th percentile draws: the UN's shape, rescaled.
On the right, the probability of dying at each age on a log scale, which is
where an implausible survival schedule shows itself -- a real one is a shallow
U with a bump in young adulthood, and it should stay that way after the level
has moved.

    python scripts/plot_schedules.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.bayes import RateExtensionPolicy  # noqa: E402
from popmodel.bayes import schedules as sched  # noqa: E402
from popmodel.engine import cohort  # noqa: E402
from popmodel.ingest import uw  # noqa: E402

YEAR = 2100
PERCENTILES = (5, 50, 95)
# Red and green as a low/high pair is unreadable for the commonest form of
# colour blindness, so the line style carries the same information as the
# colour and neither is load-bearing alone.
STYLES = {
    5: ("#d73027", (0, (1, 1))),
    50: ("#4575b4", "solid"),
    95: ("#1a9850", (0, (5, 1.5))),
}

# The open-ended 100+ ratio is T(100)/T(99), not a one-year death probability,
# so it is not comparable with the ages below it and is left off the chart.
PLOT_AGES = cohort.MAX_AGE


def death_probability(sx: np.ndarray) -> np.ndarray:
    """One minus the survival ratio into each single year of age."""
    return 1.0 - sx[:PLOT_AGES]


def panel_for(directory: Path, converter, axes) -> str:
    export = uw.validate_uw_export(directory)
    draws = list(export)
    year_index = int(np.where(draws[0].years == YEAR)[0][0])

    # Rank the draws by their 2100 total fertility, and again by female life
    # expectancy, so each panel shows its own tails rather than one ordering
    # imposed on both.
    tfr_2100 = np.array([float(d.tfr[year_index, 0]) for d in draws])
    e0_2100 = np.array([float(d.e0_female[year_index, 0]) for d in draws])
    fert_order = np.argsort(tfr_2100)
    mort_order = np.argsort(e0_2100)

    ages = np.arange(cohort.N_AGES)
    fert_ages = slice(cohort.FERT_AGE_MIN, cohort.FERT_AGE_MAX + 1)

    reference_asfr, reference_sx, _ = converter.reference.select(
        np.array([YEAR]), (export.iso3,)
    )
    axes[0].plot(
        ages[fert_ages],
        reference_asfr[0, 0][fert_ages],
        color="0.35", lw=2.2, ls="--", label="UN medium", zorder=5,
    )
    axes[1].plot(
        ages[:PLOT_AGES],
        death_probability(reference_sx[0, 0, cohort.FEMALE]),
        color="0.35", lw=2.2, ls="--", label="UN medium", zorder=5,
    )

    for percentile in PERCENTILES:
        colour, dashes = STYLES[percentile]
        rank = int(round((percentile / 100.0) * (len(draws) - 1)))

        fert_draw = draws[int(fert_order[rank])]
        converted = converter.convert(fert_draw)
        axes[0].plot(
            ages[fert_ages],
            converted.asfr[year_index, 0][fert_ages],
            color=colour, ls=dashes, lw=1.7,
            label=f"{percentile}th: TFR {fert_draw.tfr[year_index, 0]:.2f}",
        )

        mort_draw = draws[int(mort_order[rank])]
        converted = converter.convert(mort_draw)
        axes[1].plot(
            ages[:PLOT_AGES],
            death_probability(converted.sx[year_index, 0, cohort.FEMALE]),
            color=colour, ls=dashes, lw=1.7,
            label=f"{percentile}th: e0 {mort_draw.e0_female[year_index, 0]:.1f}",
        )

    axes[0].set_xlabel("age of mother")
    axes[0].set_ylabel("births per woman per year")
    axes[0].set_title(f"{export.country}: fertility age pattern, {YEAR}", fontsize=10)
    axes[0].legend(fontsize=7.5, frameon=False)
    axes[0].spines[["top", "right"]].set_visible(False)

    axes[1].set_yscale("log")
    axes[1].set_xlabel("age (the open 100+ group is not a one-year rate; omitted)")
    axes[1].set_ylabel("probability of dying (log scale)")
    axes[1].set_title(f"{export.country}: female mortality, {YEAR}", fontsize=10)
    axes[1].legend(fontsize=7.5, frameon=False, loc="lower right")
    axes[1].spines[["top", "right"]].set_visible(False)
    return export.country


def main() -> int:
    export_root = paths.INTERIM / "UW_WPP2024" / "exports"
    directories = sorted(d for d in export_root.glob("*") if d.is_dir())
    if not directories:
        raise SystemExit(f"no country exports under {export_root}")

    converter = sched.WppRelationalConverter(extension=RateExtensionPolicy.strict())

    fig, axes = plt.subplots(
        len(directories), 2, figsize=(10.5, 4.0 * len(directories)), squeeze=False
    )
    for row, directory in enumerate(directories):
        panel_for(directory, converter, axes[row])

    fig.suptitle(
        "What the converter does: the UN's age pattern, moved to each draw's level",
        fontsize=11.5,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    paths.OUT.mkdir(parents=True, exist_ok=True)
    png = paths.OUT / "schedules.png"
    fig.savefig(png, dpi=150)
    fig.savefig(paths.REPO_ROOT / "docs" / "schedules.svg")
    plt.close(fig)
    print(f"wrote {png}")
    print(f"wrote {paths.REPO_ROOT / 'docs' / 'schedules.svg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Store the Phase 4 ensemble as a prediction vintage. Written once, never edited.

Everything here is recorded with `is_project_claim` set to **false**. That flag
is the point of the exercise. This ensemble is UW's posterior pushed through
this project's engine: the fertility and mortality distributions are somebody
else's, and the long-run behaviour is their mean-reverting model. Grading it
later as though it were this project's own forecast would credit or blame the
project for work it did not do.

What it is instead is the baseline the mechanistic layer has to be compared
against. Recording it now, before Phase 5 exists, is what makes that comparison
mean anything: the numbers cannot be adjusted after the fact to make a
mechanism look good.

    python scripts/write_uw_vintage.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.track import vintage  # noqa: E402

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
YEARS = (2050, 2075, 2100, 2125, 2150)
COUNTRIES = ("NGA", "IND", "CHN", "USA", "JPN", "KOR", "DEU", "BRA", "PAK", "COD")

SOURCE_OF_TRUTH = (
    "future WPP revisions' own estimates for the year in question, which are a "
    "model output and not ground truth (standing instruction 3)"
)
NOT_A_PROJECT_CLAIM = (
    "not this project's claim: UW's posterior propagated through this project's "
    "engine. The long run is UW's mean-reverting model, which is the assumption "
    "standing instruction 8 declines to adopt by default."
)


def main() -> int:
    receipt = json.loads((paths.OUT / "uw_ensemble.json").read_text(encoding="utf-8"))
    totals = np.load(
        paths.OUT / "uw_ensemble_country_totals.npz", allow_pickle=False
    )
    years = totals["years"]
    locations = [str(code) for code in totals["locations"]]
    world = totals["world"]

    quantities: list[vintage.Quantity] = []
    for year in YEARS:
        index = int(np.where(years == year)[0][0])
        values = np.quantile(world[:, index], QUANTILES)
        quantities.append(
            vintage.Quantity(
                id=f"world-population-{year}",
                description=f"World population on 1 January {year}, 236 countries",
                unit="people",
                resolution_date=str(year),
                source_of_truth=SOURCE_OF_TRUTH,
                is_project_claim=False,
                kind="quantiles",
                quantiles={
                    f"{q:.2f}": float(v) for q, v in zip(QUANTILES, values)
                },
                scenario="uw-posterior-baseline",
                notes=NOT_A_PROJECT_CLAIM,
            )
        )

    index_2100 = int(np.where(years == 2100)[0][0])
    country_quantiles = totals["location_quantiles"]
    for code in COUNTRIES:
        column = locations.index(code)
        quantities.append(
            vintage.Quantity(
                id=f"population-{code}-2100",
                description=f"{code} population on 1 January 2100",
                unit="people",
                resolution_date="2100",
                source_of_truth=SOURCE_OF_TRUTH,
                is_project_claim=False,
                kind="quantiles",
                quantiles={
                    "0.05": float(country_quantiles[0, index_2100, column]),
                    "0.50": float(country_quantiles[1, index_2100, column]),
                    "0.95": float(country_quantiles[2, index_2100, column]),
                },
                scenario="uw-posterior-baseline",
                notes=(
                    f"{NOT_A_PROJECT_CLAIM} Country paths additionally depend on "
                    f"the migration scenario knob."
                ),
            )
        )

    peaks = years[np.argmax(world, axis=1)]
    quantities.append(
        vintage.Quantity(
            id="share-peaking-before-2100",
            description=(
                "Share of posterior draws whose world population peaks before 2100"
            ),
            unit="proportion of draws",
            resolution_date="2100",
            source_of_truth=SOURCE_OF_TRUTH,
            is_project_claim=False,
            kind="samples",
            samples=[float(year) for year in peaks[:1000]],
            scenario="uw-posterior-baseline",
            notes=(
                f"{NOT_A_PROJECT_CLAIM} Stored as the peak year of every draw so "
                f"the share can be recomputed for any threshold. Observed share "
                f"before 2100: {float((peaks < 2100).mean()):.3f}. Draws still "
                f"rising at {int(years[-1])} record that final year as their peak, "
                f"which is a censored observation, not a peak."
            ),
        )
    )

    record = vintage.new_vintage(
        "phase4-uw-baseline",
        "Phase 4: UW posterior propagated to 2150 (UN-equivalent baseline)",
        model_name="popmodel cohort engine with wpp2024-relational schedules",
        model_phase=4,
        data_provenance={
            "fertility_and_mortality": receipt["source"],
            "cross_country_pairing": receipt["cross_country_pairing"],
            "migration": receipt["migration"],
            "post_2100": receipt["post_2100_assumption"],
            "base_population": f"WPP 2024, 1 January {receipt['base_year']}",
            "excluded_locations": receipt["excluded_locations"],
            "draws": receipt["draws"],
            "manifests": [
                "data/manifest/uw_wpp2024_files.json",
                "data/manifest/uw_wpp2024_full_export.json",
                "data/manifest/uw_wpp2024_migration.json",
            ],
        },
        notes=(
            "The baseline Phase 5 must be compared against, recorded before "
            "Phase 5 exists so the comparison cannot be arranged after the fact. "
            "Every quantity here is marked as not a project claim."
        ),
    )
    record.quantities = quantities

    path = vintage.write(record)
    print(f"wrote {path}")
    print(f"  {len(quantities)} quantities, none marked as a project claim")
    for name, ok in vintage.verify_all():
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

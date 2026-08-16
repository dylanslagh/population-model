"""Make selection the benchmark and development pressure a stress test.

This analysis deliberately starts from the stable-low environment.  That path
retains the fertility decline already in the UN data and removes its assumed
recovery.  The mainstream population is then allowed to select on completed
family-size variation and parent-child persistence, the two independently
measured mainstream parameters.

The output asks how much *additional*, uniform decline after 2050 would cancel
that selection effect.  It does not forecast GDP or claim that any one decline
rate will occur.

    python scripts/analyze_selection_break_even.py
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_phase5  # noqa: E402
from popmodel import paths  # noqa: E402
from popmodel.mech import parameters as mech_parameters  # noqa: E402
from popmodel.mech import runs, sensitivity  # noqa: E402


END_YEAR = 2150
PRESSURE_FROM = 2050
ANALYSIS_DATE = "2026-08-14"
CV_VALUES = (0.44, 0.57, 0.80)
PERSISTENCE_VALUES = tuple(np.linspace(0.05, 0.30, 11))
OUT = paths.REFERENCE / "selection_break_even_sensitivity.json"


def with_values(base: mech_parameters.ParameterSet, **values: float):
    changed = dict(base.parameters)
    for name, value in values.items():
        changed[name] = replace(changed[name], value=float(value))
    return mech_parameters.ParameterSet(changed, base.source_path)


def population_break_even(
    *, baseline_world, bundle, migration, reference_tfr, base,
    low=0.0, high=0.08, tolerance=1e-5,
):
    """The decline rate that returns the 2150 *population* to the benchmark.

    The fertility boundary and this one answer different questions, and
    conflating them overstates what the fertility boundary shows. Setting the
    terminal fertility multiplier back to one still leaves every extra birth
    selection produced along the way, and those people and their descendants are
    still alive in 2150. Cancelling the population therefore takes a larger
    decline than cancelling the rate, and the gap between the two numbers is the
    accumulated stock.
    """
    scenario = runs.MechScenario(
        "population-break-even", "continued-pressure", "mainstream"
    )

    def world_at(rate: float) -> float:
        parameters = with_values(base, development_decline_per_decade=rate)
        result = run_scenario(
            scenario, bundle=bundle, migration=migration,
            reference_tfr=reference_tfr, parameters=parameters,
        )
        return float(result.world[-1])

    at_low, at_high = world_at(low), world_at(high)
    if not (at_high <= baseline_world <= at_low):
        raise RuntimeError(
            f"the benchmark {baseline_world / 1e9:.3f}bn is not bracketed by "
            f"{at_high / 1e9:.3f}-{at_low / 1e9:.3f}bn over decline rates "
            f"{low:.3f}-{high:.3f}; widen the search rather than reporting an edge"
        )
    iterations = 0
    while high - low > tolerance:
        mid = 0.5 * (low + high)
        if world_at(mid) > baseline_world:
            low = mid
        else:
            high = mid
        iterations += 1
    rate = 0.5 * (low + high)
    return {
        "break_even_decline_per_decade": rate,
        "world_2150_billions_at_break_even": world_at(rate) / 1e9,
        "benchmark_world_2150_billions": baseline_world / 1e9,
        "bisection_iterations": iterations,
        "meaning": (
            "the uniform additional decline after 2050 at which the selection "
            "run's 2150 world population equals the no-selection benchmark; "
            "larger than the fertility boundary because cancelling the terminal "
            "rate leaves the extra people selection has already produced"
        ),
    }


def run_scenario(scenario, *, bundle, migration, reference_tfr, parameters):
    return runs.run(
        scenario,
        bundle=bundle,
        parameters=parameters,
        reference_tfr=reference_tfr,
        asfr=bundle.asfr,
        sx=bundle.sx,
        srb=bundle.srb,
        migration=migration,
        years=bundle.years,
        end_year=END_YEAR,
    )[0]


def main() -> int:
    base = mech_parameters.load()
    bundle, migration = run_phase5.load_inputs()
    reference_tfr = bundle.asfr.sum(axis=2)
    stable_off = runs.MechScenario(
        "stable-low-no-selection", "stable-low", "off"
    )
    stable_mainstream = runs.MechScenario(
        "selection-only-mainstream", "stable-low", "mainstream"
    )

    started = time.time()
    baseline = run_scenario(
        stable_off, bundle=bundle, migration=migration,
        reference_tfr=reference_tfr, parameters=base,
    )
    # Fixed counterfactual weights keep the boundary about fertility rather
    # than letting a scenario change the countries used to aggregate itself.
    rate_years = baseline.years[:-1]
    baseline_weights = baseline.births / np.maximum(
        baseline.births.sum(axis=1, keepdims=True), 1e-12
    )

    rows = []
    central_mainstream = None
    for cv in CV_VALUES:
        for persistence in PERSISTENCE_VALUES:
            parameters = with_values(
                base,
                mainstream_propensity_cv=cv,
                mainstream_persistence=persistence,
            )
            result = run_scenario(
                stable_mainstream, bundle=bundle, migration=migration,
                reference_tfr=reference_tfr, parameters=parameters,
            )
            country_effect = result.selection_effect()
            world_effect = (country_effect * baseline_weights).sum(axis=1)
            final_effect = float(world_effect[-1])
            final_rate_year = int(rate_years[-1])
            decades = (final_rate_year - PRESSURE_FROM) / 10.0
            boundary = float(sensitivity.break_even_rate(final_effect, decades))
            rows.append({
                "mainstream_propensity_cv": float(cv),
                "mainstream_persistence": float(persistence),
                "selection_effect_final": final_effect,
                "final_rate_year": final_rate_year,
                "break_even_decline_per_decade": boundary,
            })
            if abs(cv - 0.57) < 1e-12 and abs(persistence - 0.15) < 1e-12:
                central_mainstream = result
        print(f"  completed persistence grid for family-size CV {cv:.2f}")

    if central_mainstream is None:
        raise RuntimeError("the sensitivity grid omitted the central parameter pair")

    stable_full = run_scenario(
        runs.GRID["selection-rebound"], bundle=bundle, migration=migration,
        reference_tfr=reference_tfr, parameters=base,
    )
    race = run_scenario(
        runs.GRID["race"], bundle=bundle, migration=migration,
        reference_tfr=reference_tfr, parameters=base,
    )
    ladder = [
        {
            "key": "stable-low-no-selection",
            "label": "Stable-low environment, no selection",
            "world_2150_billions": float(baseline.world[-1] / 1e9),
            "basis": "benchmark",
        },
        {
            "key": "selection-only-mainstream",
            "label": "Add measured mainstream selection",
            "world_2150_billions": float(central_mainstream.world[-1] / 1e9),
            "basis": "two verified sourced parameters plus a fixed three-bin approximation",
        },
        {
            "key": "selection-only-full",
            "label": "Add named groups (one routing knob)",
            "world_2150_billions": float(stable_full.world[-1] / 1e9),
            "basis": "sourced group inputs plus a defector-routing knob",
        },
        {
            "key": "race-four-percent",
            "label": "Then impose 4% development pressure",
            "world_2150_billions": float(race.world[-1] / 1e9),
            "basis": "illustrative scenario knob",
        },
    ]
    for index, row in enumerate(ladder):
        row["change_from_previous_billions"] = (
            None if index == 0 else
            row["world_2150_billions"] - ladder[index - 1]["world_2150_billions"]
        )

    print("  bisecting for the population break-even...")
    population_boundary = population_break_even(
        baseline_world=float(baseline.world[-1]), bundle=bundle,
        migration=migration, reference_tfr=reference_tfr, base=base,
    )

    payload = {
        "generated": ANALYSIS_DATE,
        "population_break_even": population_boundary,
        "benchmark": (
            "stable-low fertility environment with no additional post-2050 "
            "decline; selection is then added"
        ),
        "boundary": (
            "the uniform proportional decline per decade after 2050 that "
            "exactly cancels the mainstream selection multiplier in the final "
            "fertility-rate year"
        ),
        "aggregation": (
            "country selection effects weighted by births in the stable-low, "
            "no-selection counterfactual, so scenarios do not choose their own weights"
        ),
        "economic_claim": (
            "none: additional development pressure is a stress-test axis, not "
            "a forecast of GDP or social conditions"
        ),
        "pressure_from": PRESSURE_FROM,
        "pressure_range_per_decade": [0.0, 0.04],
        "cv_values": list(CV_VALUES),
        "persistence_values": list(PERSISTENCE_VALUES),
        "rows": rows,
        "model_ladder": ladder,
        "parameter_caveat": base.caveat(),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    central = next(
        row for row in rows
        if abs(row["mainstream_propensity_cv"] - 0.57) < 1e-12
        and abs(row["mainstream_persistence"] - 0.15) < 1e-12
    )
    print(
        f"central mainstream selection effect {central['selection_effect_final']:.3f}; "
        f"break-even additional decline "
        f"{100 * central['break_even_decline_per_decade']:.2f}% per decade "
        f"to cancel the terminal fertility rate, "
        f"{100 * population_boundary['break_even_decline_per_decade']:.2f}% "
        f"to cancel the 2150 population"
    )
    for row in ladder:
        delta = row["change_from_previous_billions"]
        print(
            f"  {row['label']:<42} {row['world_2150_billions']:.3f}bn"
            + ("" if delta is None else f"  ({delta:+.3f})")
        )
    print(f"wrote {OUT}")
    print(f"completed in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

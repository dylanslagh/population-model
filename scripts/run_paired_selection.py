"""Run the stable-low selection comparison on shared stochastic migration paths.

The selection model forks in 2024.  In each pair, the reference and mainstream
selection cases receive the same UW bayesMig trajectory through 2100 and the
same seeded AR(1) continuation afterwards.  They must nevertheless balance
that shared raw rate path against their own evolving populations; the recorded
balancing adjustment is therefore part of the result, not a hidden detail.

    python scripts/run_paired_selection.py --draws 25  # predictive check
    python scripts/run_paired_selection.py             # all 1,000 paths
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import migration, paths  # noqa: E402
from popmodel.ingest import uw_mig, wpp  # noqa: E402
from popmodel.mech import parameters as mech_parameters, runs, sensitivity  # noqa: E402


END_YEAR = 2150
PRESSURE_FROM = 2050
REFERENCE = runs.MechScenario("stable-low-no-selection", "stable-low", "off")
SELECTION = runs.MechScenario(
    "selection-only-mainstream", "stable-low", "mainstream"
)


def aligned_rates(raw: migration.RawMigrationPath, bundle) -> tuple[np.ndarray, np.ndarray]:
    """Put UW's 236 paths into WPP's complete 237-country state.

    Vatican City is deliberately retained, with zero migration, rather than
    disappearing from a world total because UW does not publish its path.
    """
    source = {int(code): i for i, code in enumerate(raw.loc_id)}
    rates = np.zeros((len(raw.years), len(bundle.loc_id)), dtype=np.float64)
    active = np.zeros(len(bundle.loc_id), dtype=bool)
    missing = []
    for column, code in enumerate(bundle.loc_id):
        source_column = source.get(int(code))
        if source_column is None:
            missing.append(bundle.iso3[column])
            continue
        rates[:, column] = raw.rates[:, source_column]
        active[column] = True
    if missing != ["VAT"]:
        raise ValueError(f"unexpected UW migration omissions: {', '.join(missing)}")
    return rates, active


def world_selection_effect(reference, selected) -> np.ndarray:
    """Keep the counterfactual country weights fixed across the pair."""
    weights = reference.births / np.maximum(reference.births.sum(axis=1, keepdims=True), 1e-12)
    return (selected.selection_effect() * weights).sum(axis=1)


def quantiles(values: np.ndarray) -> dict[str, list[float]]:
    return {
        label: np.quantile(values, probability, axis=0).tolist()
        for label, probability in (("p05", 0.05), ("p50", 0.50), ("p95", 0.95))
    }


def compact_receipt(receipt: dict) -> dict:
    """Round bookkeeping values only after their assertions have run."""
    return {
        **receipt,
        "maximum_world_imbalance_people": round(receipt["maximum_world_imbalance_people"], 8),
        "maximum_rate_adjustment": receipt["maximum_rate_adjustment"],
        "total_absolute_adjustment_people": receipt["total_absolute_adjustment_people"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument("--migration-seed", type=int, default=migration.DEFAULT_SEED)
    args = parser.parse_args()
    if args.draws < 1:
        raise ValueError("--draws must be positive")
    if args.end_year <= 2024:
        raise ValueError("--end-year must be after the 2024 selection fork")

    started = time.time()
    bundle = wpp.load_bundle()
    source = uw_mig.load()
    if tuple(source.locations) != tuple(bundle.iso3):
        raise ValueError("stored migration composition is not in WPP location order")
    csv_path = paths.INTERIM / "UW_WPP2024" / "migration" / "ascii_trajectories.csv"
    print("reading UW migration trajectories")
    draws = uw_mig.read_rate_draws(csv_path, source.rates)
    if args.draws > len(draws.trajectory_ids):
        raise ValueError(f"requested {args.draws} paths; source has only {len(draws.trajectory_ids)}")
    fitted = migration.fit_late_ar1(draws)
    continuation = migration.simulate_ar1_continuation(
        draws, fitted, end_rate_year=args.end_year - 1, seed=args.migration_seed
    )

    parameters = mech_parameters.load()
    reference_tfr = bundle.asfr.sum(axis=2)
    trajectory_ids = draws.trajectory_ids[:args.draws]
    n_years = args.end_year - int(bundle.years[0])
    n_locations = len(bundle.iso3)
    reference_totals = np.empty((args.draws, n_years + 1, n_locations), dtype=np.float32)
    selection_totals = np.empty_like(reference_totals)
    selection_effects = np.empty((args.draws, n_years), dtype=np.float64)
    pair_receipts = []

    for index, trajectory_id in enumerate(trajectory_ids):
        raw = migration.trajectory_path(
            draws, continuation, trajectory_id=int(trajectory_id),
            start_rate_year=int(bundle.years[0]), end_rate_year=args.end_year - 1,
        )
        rates, active = aligned_rates(raw, bundle)
        reference_policy = migration.BalancedMigrationPath(
            raw=raw, rates=rates, composition=source.composition,
            active_locations=active, locations=tuple(bundle.iso3),
        )
        selection_policy = migration.BalancedMigrationPath(
            raw=raw, rates=rates, composition=source.composition,
            active_locations=active, locations=tuple(bundle.iso3),
        )
        reference_result, _ = runs.run(
            REFERENCE, bundle=bundle, parameters=parameters, reference_tfr=reference_tfr,
            asfr=bundle.asfr, sx=bundle.sx, srb=bundle.srb,
            migration=reference_policy, years=bundle.years, end_year=args.end_year,
        )
        selection_result, _ = runs.run(
            SELECTION, bundle=bundle, parameters=parameters, reference_tfr=reference_tfr,
            asfr=bundle.asfr, sx=bundle.sx, srb=bundle.srb,
            migration=selection_policy, years=bundle.years, end_year=args.end_year,
        )
        reference_receipt = reference_policy.receipt()
        selection_receipt = selection_policy.receipt()
        if (
            reference_receipt["source_trajectory_id"] != selection_receipt["source_trajectory_id"]
            or reference_receipt["continuation_seed"] != selection_receipt["continuation_seed"]
        ):
            raise RuntimeError("paired cases did not receive the same raw migration path")
        if (
            reference_receipt["maximum_world_imbalance_people"] > 1e-5
            or selection_receipt["maximum_world_imbalance_people"] > 1e-5
        ):
            raise RuntimeError("world migration did not balance to numerical precision")
        reference_totals[index] = reference_result.population
        selection_totals[index] = selection_result.population
        selection_effects[index] = world_selection_effect(reference_result, selection_result)
        pair_receipts.append({
            "source_trajectory_id": int(trajectory_id),
            "reference": compact_receipt(reference_receipt),
            "selection": compact_receipt(selection_receipt),
        })
        if (index + 1) % max(1, min(25, args.draws)) == 0:
            print(f"  paired paths: {index + 1}/{args.draws}")

    years = np.arange(int(bundle.years[0]), args.end_year + 1, dtype=np.int64)
    final_effect = selection_effects[:, -1]
    decades = (int(years[-2]) - PRESSURE_FROM) / 10.0
    break_even = np.array([sensitivity.break_even_rate(value, decades) for value in final_effect])
    legacy = json.loads((paths.REFERENCE / "selection_break_even_sensitivity.json").read_text())
    central_legacy = next(
        row["break_even_decline_per_decade"] for row in legacy["rows"]
        if abs(row["mainstream_propensity_cv"] - 0.57) < 1e-12
        and abs(row["mainstream_persistence"] - 0.15) < 1e-12
    )

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": {
            "selection_fork": int(bundle.years[0]),
            "reference": REFERENCE.describe(),
            "selection": SELECTION.describe(),
            "shared_path": (
                "same UW source trajectory through 2100 and same seeded AR(1) "
                "continuation afterwards; each case balances that raw path against "
                "its own evolving population"
            ),
            "migration_continuation": fitted.source,
            "migration_seed": int(args.migration_seed),
            "source_trajectory_ids": [int(v) for v in trajectory_ids],
        },
        "acceptance_checks": {
            "neutral_typed_engine": (
                "covered by tests/test_paired_migration.py: neutral typed engine "
                "equals the ordinary cohort engine with state-aware migration"
            ),
            "shared_source_and_seed": True,
            "maximum_world_imbalance_people": max(
                max(row["reference"]["maximum_world_imbalance_people"], row["selection"]["maximum_world_imbalance_people"])
                for row in pair_receipts
            ),
            "no_clipped_emigration": "age/sex allocation redistributes infeasible removals before the engine sees them",
        },
        "years": years.tolist(),
        "world_population_billions": {
            "reference": quantiles(reference_totals.sum(axis=2) / 1e9),
            "selection": quantiles(selection_totals.sum(axis=2) / 1e9),
            "selection_minus_reference_2150": quantiles(
                (selection_totals[:, -1].sum(axis=1) - reference_totals[:, -1].sum(axis=1))[:, None] / 1e9
            ),
        },
        "country_population": {
            "locations": list(bundle.iso3),
            "reference": quantiles(reference_totals),
            "selection": quantiles(selection_totals),
        },
        "selection_effect": quantiles(selection_effects),
        "break_even_additional_decline_per_decade": {
            **{label: value[0] for label, value in quantiles(break_even[:, None]).items()},
            "legacy_deterministic": central_legacy,
            "difference_from_legacy_median": float(np.median(break_even) - central_legacy),
            "interpretation": (
                "movement from the deterministic value is caused by paired stochastic "
                "migration and its population-dependent balancing adjustment; mechanism "
                "parameters and the stable-low fertility environment are unchanged"
            ),
        },
        "paired_migration_receipts": pair_receipts,
        "parameter_caveat": parameters.caveat(),
    }
    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "paired_selection_migration.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"  2150 selection minus reference: "
        f"{np.median(selection_totals[:, -1].sum(axis=1) - reference_totals[:, -1].sum(axis=1)) / 1e9:+.3f}bn"
    )
    print(
        f"  break-even additional decline: {100 * np.median(break_even):.2f}% per decade "
        f"(legacy deterministic {100 * central_legacy:.2f}%)"
    )
    print(f"wrote {out.relative_to(paths.REPO_ROOT)}")
    print(f"completed in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

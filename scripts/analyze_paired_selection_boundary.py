"""Robustness receipt for the universal-pressure selection boundary.

This does not add a type-specific economic mechanism. It reuses the stated
family-size-spread and parent-child-persistence grid, while pairing every
selection run to the same stratified sample of stochastic migration paths.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_paired_selection as paired  # noqa: E402
from popmodel import migration, paths  # noqa: E402
from popmodel.ingest import uw_mig, wpp  # noqa: E402
from popmodel.mech import parameters as mech_parameters, runs, sensitivity  # noqa: E402

END_YEAR = 2150
PRESSURE_FROM = 2050
REFERENCE = runs.MechScenario("stable-low-no-selection", "stable-low", "off")
SELECTION = runs.MechScenario("selection-only-mainstream", "stable-low", "mainstream")


def with_values(base, **values):
    changed = dict(base.parameters)
    for name, value in values.items():
        changed[name] = replace(changed[name], value=float(value))
    return mech_parameters.ParameterSet(changed, base.source_path)


def q(values):
    values = np.asarray(values, dtype=float)
    return {key: float(np.quantile(values, level)) for key, level in (("p05", .05), ("p50", .5), ("p95", .95))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration-draws", type=int, default=50)
    parser.add_argument("--migration-seed", type=int, default=migration.DEFAULT_SEED)
    args = parser.parse_args()
    if args.migration_draws < 3:
        raise ValueError("at least three stratified migration paths are required")
    started = time.time()
    legacy = json.loads((paths.REFERENCE / "selection_break_even_sensitivity.json").read_text())
    cvs, persistences = legacy["cv_values"], legacy["persistence_values"]
    base = mech_parameters.load()
    bundle, source = wpp.load_bundle(), uw_mig.load()
    if tuple(source.locations) != tuple(bundle.iso3):
        raise ValueError("migration composition is not in WPP location order")
    raw_draws = uw_mig.read_rate_draws(paths.INTERIM / "UW_WPP2024" / "migration" / "ascii_trajectories.csv", source.rates)
    selected = np.rint(np.linspace(0, len(raw_draws.trajectory_ids) - 1, args.migration_draws)).astype(int)
    if len(np.unique(selected)) != len(selected):
        raise ValueError("stratified migration sample contains duplicate paths")
    continuation = migration.simulate_ar1_continuation(raw_draws, migration.fit_late_ar1(raw_draws), end_rate_year=2149, seed=args.migration_seed)
    ref_tfr = bundle.asfr.sum(axis=2)
    raw_paths = []
    reference_weights = []
    for index in selected:
        raw = migration.trajectory_path(raw_draws, continuation, trajectory_id=int(raw_draws.trajectory_ids[index]), start_rate_year=2024, end_rate_year=2149)
        rates, active = paired.aligned_rates(raw, bundle)
        policy = migration.BalancedMigrationPath(raw=raw, rates=rates, composition=source.composition, active_locations=active, locations=tuple(bundle.iso3))
        result, _ = runs.run(REFERENCE, bundle=bundle, parameters=base, reference_tfr=ref_tfr, asfr=bundle.asfr, sx=bundle.sx, srb=bundle.srb, migration=policy, years=bundle.years, end_year=END_YEAR)
        policy.receipt()
        raw_paths.append((raw, rates, active))
        reference_weights.append(result.births / np.maximum(result.births.sum(axis=1, keepdims=True), 1e-12))
    rows = []
    for cv in cvs:
        for persistence in persistences:
            parameters = with_values(base, mainstream_propensity_cv=cv, mainstream_persistence=persistence)
            boundaries = []
            for (raw, rates, active), weights in zip(raw_paths, reference_weights):
                policy = migration.BalancedMigrationPath(raw=raw, rates=rates, composition=source.composition, active_locations=active, locations=tuple(bundle.iso3))
                result, _ = runs.run(SELECTION, bundle=bundle, parameters=parameters, reference_tfr=ref_tfr, asfr=bundle.asfr, sx=bundle.sx, srb=bundle.srb, migration=policy, years=bundle.years, end_year=END_YEAR)
                receipt = policy.receipt()
                if receipt["maximum_world_imbalance_people"] > 1e-5:
                    raise RuntimeError("paired migration did not balance")
                effect = float((result.selection_effect() * weights).sum(axis=1)[-1])
                boundaries.append(sensitivity.break_even_rate(effect, (2149 - PRESSURE_FROM) / 10))
            rows.append({"mainstream_propensity_cv": float(cv), "mainstream_persistence": float(persistence), "break_even_decline_per_decade": q(boundaries)})
        print(f"  completed CV {cv:.2f}")
    central = next(
        row for row in rows
        if abs(row["mainstream_propensity_cv"] - .57) < 1e-12
        and abs(row["mainstream_persistence"] - .15) < 1e-12
    )
    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "purpose": "Universal additional pressure after 2050 that cancels mainstream selection; not an economic forecast.", "migration": {"paths": int(args.migration_draws), "selection": "equally spaced source trajectory IDs", "trajectory_ids": [int(raw_draws.trajectory_ids[i]) for i in selected], "continuation_seed": args.migration_seed, "pairing": "reference and selection share each raw path and continuation innovations; balancing remains population-specific and is asserted"}, "parameter_grid": {"cv_values": cvs, "persistence_values": persistences}, "rows": rows, "central_result": central, "parameter_caveat": base.caveat()}
    target = paths.REFERENCE / "paired_selection_boundary_sensitivity.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"central paired boundary: {100 * central['break_even_decline_per_decade']['p50']:.2f}% per decade")
    print(f"wrote {target.relative_to(paths.REPO_ROOT)} in {time.time() - started:.0f}s")

if __name__ == "__main__":
    main()

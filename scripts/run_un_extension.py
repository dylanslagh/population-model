"""Build the project-owned extension of the UN reproduction from 2100 to 2150.

The boundary is deliberate:

* 2024-2100 is the published WPP 2024 medium path.
* 2100-2150 is this project's extension.  Fertility, mortality and the sex
  ratio are held at their final WPP schedules.  Migration is stochastic.

UW's public bayesMig archive supplies 1,000 net-migration-rate paths through
2100 but not the fitted MCMC state needed to ask it for another fifty years.
The extension therefore fits the same AR(1) form to the late portion of those
paths, begins each continuation at its own published 2100 value, and simulates
to 2149.  Every projected year is balanced so world net migration is zero.

This is a model-output emulator and a project extension, never an official UN
projection to 2150.

    python scripts/run_un_extension.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import migration, paths  # noqa: E402
from popmodel.ingest import uw_mig, wpp  # noqa: E402

OFFICIAL_END = 2100
END_YEAR = 2150
QUANTILE_LEVELS = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
WATCH = ("USA", "CAN", "ARE", "JPN", "NGA", "DEU")


def quantile_summary(values: np.ndarray) -> dict[str, float]:
    q = np.quantile(values, (0.05, 0.5, 0.95))
    return {"p05": float(q[0]), "p50": float(q[1]), "p95": float(q[2])}


def main() -> int:
    started = time.time()
    bundle = wpp.load_bundle()
    source = uw_mig.load()
    csv_path = paths.INTERIM / "UW_WPP2024" / "migration" / "ascii_trajectories.csv"

    print("reading all 1,000 UW bayesMig trajectories")
    draws = uw_mig.read_rate_draws(csv_path, source.rates)
    print(f"  {draws.rates.shape[0]:,} draws x {draws.rates.shape[2]} locations")

    fitted = migration.fit_late_ar1(draws)
    simulated = migration.simulate_ar1_continuation(
        draws, fitted, end_rate_year=END_YEAR - 1
    )
    print(
        f"  AR(1) fit {fitted.fit_start_year}-{fitted.fit_end_year}; "
        f"{fitted.phi_clipped} of {len(fitted.phi)} persistence estimates bounded"
    )
    print(
        f"  generated {simulated.generated_values:,} future rates; "
        f"{simulated.clipped_values:,} hit the +/-{uw_mig.RATE_LIMIT:g} safety limit"
    )

    # Align UW's 236 locations to WPP's complete 237-location state.  Holy See
    # is the one documented absence.  It receives zero migration and is kept in
    # every world total rather than silently dropped.
    source_column = {int(code): i for i, code in enumerate(simulated.loc_id)}
    rate_paths = np.zeros(
        (len(simulated.trajectory_ids), len(simulated.years), len(bundle.loc_id)),
        dtype=np.float32,
    )
    active = np.zeros(len(bundle.loc_id), dtype=bool)
    missing = []
    for j, code in enumerate(bundle.loc_id):
        column = source_column.get(int(code))
        if column is None:
            missing.append(bundle.iso3[j])
            continue
        rate_paths[:, :, j] = simulated.rates[:, :, column]
        active[j] = True
    if missing != ["VAT"]:
        raise SystemExit(f"unexpected migration-source omissions: {', '.join(missing)}")
    if tuple(source.locations) != tuple(bundle.iso3):
        raise SystemExit("stored age/sex migration composition is not in WPP location order")

    countries = pd.DataFrame(
        {"LocID": bundle.loc_id, "ISO3_code": bundle.iso3, "Location": bundle.name}
    )
    official = wpp.medium_population(countries, bundle.years)
    if int(bundle.years[-1]) != OFFICIAL_END:
        raise SystemExit(
            f"WPP boundary changed from {OFFICIAL_END} to {int(bundle.years[-1])}; "
            "review the extension rather than silently moving it"
        )

    print("projecting the post-2100 extension")
    result = migration.project_extension(
        official[-1],
        start_year=OFFICIAL_END,
        end_year=END_YEAR,
        sx=bundle.sx[-1],
        asfr=bundle.asfr[-1],
        srb=bundle.srb[-1],
        rate_years=simulated.years,
        rate_paths=rate_paths,
        composition=source.composition,
        locations=tuple(bundle.iso3),
        trajectory_ids=simulated.trajectory_ids,
        active_locations=active,
    )

    location_quantiles = np.quantile(result.location_totals, QUANTILE_LEVELS, axis=0)
    world_quantiles = np.quantile(result.world, QUANTILE_LEVELS, axis=0)
    official_world = official.sum(axis=(1, 2, 3))

    print("\nworld population, billions")
    for year in (2100, 2125, 2150):
        i = int(np.where(result.years == year)[0][0])
        q = world_quantiles[[0, 3, 6], i] / 1e9
        print(f"  {year}: {q[1]:.3f}  (90% {q[0]:.3f}-{q[2]:.3f})")
    print(
        f"  maximum annual world migration imbalance: "
        f"{result.maximum_world_imbalance_people:.6f} people"
    )

    country_summary = {}
    for iso3 in WATCH:
        j = bundle.iso3.index(iso3)
        country_summary[iso3] = {
            "name": bundle.name[j],
            "population_2100": float(result.location_totals[0, 0, j]),
            "population_2150": quantile_summary(result.location_totals[:, -1, j]),
        }

    archive_manifest = json.loads(
        (paths.MANIFEST / "uw_wpp2024_migration.json").read_text(encoding="utf-8")
    )
    receipt = {
        "model_structure": {
            "un_reproduction": "WPP 2024 medium path through 2100 only",
            "project_extension": "starts from the WPP population on 1 January 2100 and runs to 2150",
            "official_boundary": OFFICIAL_END,
        },
        "post_2100_fertility": "final WPP age-specific fertility schedule held constant",
        "post_2100_mortality": "final WPP age-specific survival schedule held constant",
        "migration": {
            "source": uw_mig.SOURCE_LABEL,
            "source_archive_sha256": archive_manifest["archive"]["sha256"],
            "source_trajectories": int(len(draws.trajectory_ids)),
            "source_end_year": int(draws.years[-1]),
            "continuation": fitted.source,
            "equation": "r[t] = mu + phi * (r[t-1] - mu) + Normal(0, sigma)",
            "fit_years": [fitted.fit_start_year, fitted.fit_end_year],
            "seed": simulated.seed,
            "rate_limit": uw_mig.RATE_LIMIT,
            "generated_values": simulated.generated_values,
            "clipped_values": simulated.clipped_values,
            "global_balance": (
                "each draw-year is shifted by a common rate across active countries, "
                "equivalent to redistributing the count discrepancy by current population; "
                "world net migration is zero"
            ),
            "maximum_world_imbalance_people": result.maximum_world_imbalance_people,
            "age_sex_composition": (
                "borrowed from the absolute UN medium-path migration residual; impossible "
                "emigration cells are redistributed across populated cells"
            ),
            "redistributed_outflow_cells": result.redistributed_outflow_cells,
            "missing_location": "Holy See: retained in the population with zero migration",
            "claim_boundary": (
                "the public archive omits the fitted MCMC state; this is an AR(1) "
                "emulator of its late-horizon trajectories, not an official UN continuation"
            ),
        },
        "world_population_billions": {
            str(year): {
                key: value / 1e9
                for key, value in quantile_summary(
                    result.world[:, int(np.where(result.years == year)[0][0])]
                ).items()
            }
            for year in (2100, 2125, 2150)
        },
        "watch_countries": country_summary,
    }

    paths.OUT.mkdir(parents=True, exist_ok=True)
    out_json = paths.OUT / "un_project_extension.json"
    out_npz = paths.OUT / "un_project_extension_country_totals.npz"
    out_json.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(
        out_npz,
        official_years=bundle.years,
        official_world=official_world,
        extension_years=result.years,
        locations=np.array(result.locations),
        quantile_levels=QUANTILE_LEVELS,
        location_quantiles=location_quantiles,
        world=result.world,
    )
    reference = paths.REFERENCE / "un_project_extension_summary.json"
    reference.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out_json.relative_to(paths.REPO_ROOT)}")
    print(f"wrote {out_npz.relative_to(paths.REPO_ROOT)}")
    print(f"wrote {reference.relative_to(paths.REPO_ROOT)}")
    print(f"completed in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

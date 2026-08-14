"""Where the width of the band actually comes from.

The band on the map says the answer is uncertain. It does not say what we are
uncertain *about*, and those are different claims with different remedies. This
holds every component at its median except one, varies that one across its own
draws, and measures how much of the width it accounts for.

Five sources, each isolated:

* **fertility** -- UW's posterior for total fertility.
* **mortality** -- UW's posterior for life expectancy.
* **migration** -- UW's bayesMig trajectories, continued after 2100 with the
  project's AR(1) emulator and balanced to zero world net migration in every
  draw-year. The published run collapses these to a median.
* **mechanism** -- Phase 5's selection and development-pressure parameters,
  taken from `out/phase5.json` rather than recomputed.
* **after the source ends** -- our own assumption that rates hold constant
  once UW stops. Measured by stopping ten years earlier, at 2090, and seeing
  how far the answer moves. This is the only source here that is nobody's data
  and entirely our choice.

Two things are expected before running it, and worth checking against:

* Migration should be near-invisible in the **world** total and large for
  individual countries. It has to cancel globally.
* The mechanism should dominate everything at 2150. If it does not, the
  project's central claim is weaker than it thinks.

Isolating a source means holding the others at a median trajectory, which is
not itself a draw. That is a real approximation: it measures each source's
contribution around the centre, not its interaction with the others.

    python scripts/decompose_uncertainty.py --draws 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import migration as migration_model  # noqa: E402
from popmodel import paths  # noqa: E402
from popmodel.bayes import (  # noqa: E402
    BasePopulation,
    RateExtensionPolicy,
    TrajectoryDraw,
    propagate,
)
from popmodel.bayes import schedules as sched  # noqa: E402
from popmodel.ingest import uw_bundle, uw_mig, wpp  # noqa: E402

END_YEAR = 2150
REPORT_YEARS = (2050, 2100, 2150)
WATCH = ("CAN", "USA", "NGA", "JPN", "ARE", "PHL")
SOURCES = ("fertility", "mortality", "migration", "everything", "stop-at-2090")

POST_2100 = (
    "UW's trajectories end in 2100; the final year's rates are held constant "
    "thereafter. This is an assumption of this project, not of the source."
)


def median_component(values: np.ndarray) -> np.ndarray:
    """The median trajectory, per year and country. Not itself a draw."""
    return np.median(values, axis=2)


def build_base(bundle):
    reference = wpp.load_bundle()
    index = {code: i for i, code in enumerate(reference.iso3)}
    columns = np.array([index[code] for code in bundle.iso3])
    return BasePopulation(
        year=int(reference.years[0]),
        locations=bundle.iso3,
        values=reference.pop_base[columns],
        source_revision=str(reference.provenance["revision_label"]),
        source="WPP 2024 population by single age and sex, 1 January 2024",
    ), reference, columns


def make_draw(template: TrajectoryDraw, *, tfr, e0f, e0m, draw_id) -> TrajectoryDraw:
    return TrajectoryDraw(
        draw_id=draw_id,
        years=template.years,
        locations=template.locations,
        tfr=tfr,
        e0_female=e0f,
        e0_male=e0m,
        draw_kind=template.draw_kind,
        weight=template.weight,
        provenance=template.provenance,
    )


def mechanism_from_phase5() -> dict | None:
    """Read the mechanism width, which Phase 5 computes independently."""
    phase5 = paths.OUT / "phase5.json"
    if not phase5.exists():
        return None
    payload = json.loads(phase5.read_text(encoding="utf-8"))
    band = payload.get("ensemble", {}).get("race", {}).get("world_2150_billions")
    if not band:
        return None
    return {
        "2150": band["p95"] - band["p05"],
        "draws": payload["ensemble"]["draws"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--draws", type=int, default=200)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument(
        "--refresh-mechanism-only",
        action="store_true",
        help=(
            "reuse the existing demographic-source receipt and refresh only "
            "the independently computed Phase 5 mechanism width"
        ),
    )
    parser.add_argument(
        "--migration-only",
        action="store_true",
        help="reuse the existing receipt and replace only the corrected migration component",
    )
    args = parser.parse_args()

    if args.refresh_mechanism_only:
        out = paths.OUT / "uncertainty_decomposition.json"
        if not out.exists():
            raise FileNotFoundError(
                "no existing uncertainty decomposition to refresh; run the full command"
            )
        receipt = json.loads(out.read_text(encoding="utf-8"))
        mechanism = mechanism_from_phase5()
        if mechanism is None:
            raise FileNotFoundError(
                "out/phase5.json has no parameter ensemble; run Phase 5 first"
            )
        receipt["mechanism"] = mechanism
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(
            "refreshed mechanism width from phase5.json: "
            f"{mechanism['2150']:.2f}bn ({mechanism['draws']} draws)"
        )
        return 0

    bundle = uw_bundle.load()
    base, reference, columns = build_base(bundle)
    source = uw_mig.load()
    position = {code: i for i, code in enumerate(source.locations)}
    keep = np.array([position[code] for code in bundle.iso3])

    forecast = bundle.forecast_mask()
    tfr = bundle.tfr[forecast]
    e0f = bundle.e0_female[forecast]
    e0m = bundle.e0_male[forecast]
    median_tfr = median_component(tfr)
    median_e0f = median_component(e0f)
    median_e0m = median_component(e0m)

    template = next(iter(bundle))
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.hold_all(POST_2100)
    )

    print("reading every migration trajectory (the published run uses the median)")
    migration_csv = paths.INTERIM / "UW_WPP2024" / "migration" / "ascii_trajectories.csv"
    migration_draws = uw_mig.read_rate_draws(migration_csv, source.rates)
    migration_fit = migration_model.fit_late_ar1(migration_draws)
    migration_future = migration_model.simulate_ar1_continuation(
        migration_draws, migration_fit, end_rate_year=args.end_year - 1
    )
    print(f"  {migration_draws.rates.shape[0]} migration trajectories")

    loc_ids = np.array(
        [int(reference.loc_id[i]) for i in columns], dtype=np.int64
    )

    def migration_for(draw_index: int | None):
        rates = source.rates
        if draw_index is not None:
            rates = uw_mig.MigrationRates(
                years=rates.years,
                loc_id=rates.loc_id,
                rates=migration_draws.rates[draw_index],
                provenance=rates.provenance,
            )
        return uw_mig.build_assumption(
            rates,
            composition=source.composition[keep],
            population=source.population[:, keep],
            loc_id=loc_ids,
            locations=bundle.iso3,
            years=source.population_years,
        )

    median_migration = migration_for(None)
    n = args.draws
    results = {}
    if args.migration_only:
        existing = paths.OUT / "uncertainty_decomposition.json"
        if not existing.exists():
            raise FileNotFoundError("no existing uncertainty decomposition to update")
        previous = json.loads(existing.read_text(encoding="utf-8"))
        results = previous.get("sources", {})

    median_projection = converter.convert(make_draw(
        template,
        tfr=median_tfr,
        e0f=median_e0f,
        e0m=median_e0m,
        draw_id="median-rates-for-migration-decomposition",
    ))

    names = ("migration",) if args.migration_only else SOURCES
    for name in names:
        started = time.time()
        if name == "migration":
            # The public bayesMig paths are not globally balanced draw by draw.
            # Applying their counts as fixed arrays created/destroyed millions
            # of people in some trajectories and made the old 1.75bn world
            # width an artefact.  Rates are now applied to each path's evolving
            # population and population-weight balanced every year.
            source_before_boundary = (
                (migration_draws.years >= base.year)
                & (migration_draws.years < migration_future.years[0])
            )
            combined_years = np.concatenate(
                [migration_draws.years[source_before_boundary], migration_future.years]
            )
            combined_rates = np.concatenate(
                [migration_draws.rates[:, source_before_boundary, :], migration_future.rates],
                axis=1,
            )
            source_col = {int(code): i for i, code in enumerate(migration_draws.loc_id)}
            order = np.array([source_col[int(code)] for code in loc_ids])
            rate_paths = combined_rates[:n, :, order]
            dynamic = migration_model.project_extension(
                base.values,
                start_year=base.year,
                end_year=args.end_year,
                sx=median_projection.sx,
                asfr=median_projection.asfr,
                srb=median_projection.srb,
                rate_years=combined_years,
                rate_paths=rate_paths,
                composition=source.composition[keep],
                locations=bundle.iso3,
                trajectory_ids=migration_draws.trajectory_ids[:n],
            )
            world = dynamic.world
            totals = dynamic.location_totals
            years = dynamic.years
        else:
            # Stopping at 2090 uses the same draws and simply hands the engine
            # ten fewer years of rates, so the difference between it and
            # "everything" is purely the cost of our hold-constant rule.
            cut = len(template.years)
            if name == "stop-at-2090":
                cut = int(np.where(template.years == 2090)[0][0]) + 1
            short = TrajectoryDraw(
                draw_id=template.draw_id, years=template.years[:cut],
                locations=template.locations, tfr=template.tfr[:cut],
                e0_female=template.e0_female[:cut], e0_male=template.e0_male[:cut],
                draw_kind=template.draw_kind, weight=template.weight,
                provenance=template.provenance,
            )
            vary_f = name in ("fertility", "everything", "stop-at-2090")
            vary_m = name in ("mortality", "everything", "stop-at-2090")

            def draws():
                for d in range(n):
                    use_f = (tfr[:cut, :, d] if vary_f else median_tfr[:cut])
                    use_mf = (e0f[:cut, :, d] if vary_m else median_e0f[:cut])
                    use_mm = (e0m[:cut, :, d] if vary_m else median_e0m[:cut])
                    yield converter.convert(make_draw(
                        short, tfr=use_f, e0f=use_mf, e0m=use_mm,
                        draw_id=f"{name}-{d:04d}",
                    ))

            ensemble = propagate(
                base, draws(), end_year=args.end_year, migration=median_migration
            )
            world = ensemble.world
            totals = ensemble.location_totals
            years = ensemble.years

        def width(values, axis_years, year):
            i = int(np.where(axis_years == year)[0][0])
            column = values[:, i] if values.ndim == 2 else values[:, i]
            lo, hi = np.quantile(column, (0.05, 0.95))
            return float(hi - lo)

        entry = {
            "world_width_billions": {
                str(y): width(world, years, y) / 1e9 for y in REPORT_YEARS
            },
            "world_median_billions": {
                str(y): float(np.median(world[:, int(np.where(years == y)[0][0])]) / 1e9)
                for y in REPORT_YEARS
            },
            "countries_2100_width_millions": {},
            "seconds": round(time.time() - started, 1),
            "draws": n,
        }
        if name == "migration":
            entry["global_balance"] = (
                "zero world net migration in every draw-year, redistributed by "
                "each path's evolving population"
            )
            entry["maximum_world_imbalance_people"] = dynamic.maximum_world_imbalance_people
            entry["post_2100"] = migration_fit.source
        index_2100 = int(np.where(years == 2100)[0][0])
        for iso3 in WATCH:
            if iso3 not in bundle.iso3:
                continue
            j = bundle.iso3.index(iso3)
            column = totals[:, index_2100, j]
            lo, hi = np.quantile(column, (0.05, 0.95))
            entry["countries_2100_width_millions"][iso3] = float(hi - lo) / 1e6
        results[name] = entry
        print(
            f"  {name:<11} world 90% width: "
            + "  ".join(
                f"{y} {entry['world_width_billions'][str(y)]:.2f}bn"
                for y in REPORT_YEARS
            )
            + f"   ({entry['seconds']:.0f}s)"
        )

    both = results.get("everything"), results.get("stop-at-2090")
    if all(both):
        shift = (
            both[1]["world_median_billions"]["2150"]
            - both[0]["world_median_billions"]["2150"]
        )
        print(
            f"  {'post-2100':<11} stopping ten years earlier moves the 2150 "
            f"median by {shift:+.2f}bn"
        )
        results["stop-at-2090"]["median_shift_vs_everything_2150"] = shift

    mechanism = mechanism_from_phase5()
    if mechanism:
        print(
            f"  {'mechanism':<11} world 90% width: 2150 "
            f"{mechanism['2150']:.2f}bn   (from phase5.json)"
        )

    receipt = {
        "draws": n,
        "end_year": args.end_year,
        "method": (
            "one source varied across its own draws at a time, the others held "
            "at a median trajectory. A median trajectory is not itself a draw, "
            "so this measures each source's contribution around the centre and "
            "not its interaction with the others."
        ),
        "sources": results,
        "mechanism": mechanism,
        "mechanism_note": (
            "from Phase 5's parameter ensemble; its demographic rates are the "
            "UN medium path rather than the UW posterior, so it is not directly "
            "additive with the others"
        ),
    }
    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "uncertainty_decomposition.json"
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

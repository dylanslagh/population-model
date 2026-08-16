"""Phase 4 steps 7 and 8: the checks, then the ensemble.

This pushes UW's posterior fertility and mortality trajectories through the
deterministic engine, one draw at a time, and reports the resulting spread of
world and country populations.

Read this before reading the output
-----------------------------------
The band this produces is **not this project's uncertainty about 2150**. It is
the UN-equivalent baseline: UW's model is mean-reverting, so its long run
carries exactly the assumption standing instruction 8 says not to adopt by
default. The band is here to be argued with, and every artefact it writes says
so in its own provenance.

Three assumptions are made explicit rather than inherited, because each one
changes the answer:

* **Migration.** Not supplied by the fertility and mortality archives. It comes
  from UW's separate bayesMig source, as a median path with a borrowed age and
  sex composition, so the ensemble's spread carries fertility and mortality
  uncertainty but not migration uncertainty. See `ingest/uw_mig.py` for the
  three decisions inside that sentence. `--migration zero` runs the explicit
  no-migration comparison instead.
* **After 2100.** UW stops at 2100 and this project runs to 2150. Those fifty
  years hold the final rates constant. That is ours, not the UN's, and half the
  distance to 2150 rests on it.
* **Holy See.** In WPP's 237 countries, absent from UW's 236. It is excluded
  rather than invented, which removes about 500 people from a world total of
  ten billion.

The check comes first
---------------------
Standing instruction 6: run the predictive checks before believing anything. A
small number of draws is run and their implied world population is compared
against bounds that any sane demographic projection must satisfy. If the
ensemble implies 244 billion or 300 million, this stops before spending an hour
on the full run.

    python scripts/run_uw_ensemble.py --draws 25      # the quick check
    python scripts/run_uw_ensemble.py                 # all 1,000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.bayes import (  # noqa: E402
    BasePopulation,
    MigrationAssumption,
    RateExtensionPolicy,
    propagate,
)
from popmodel.bayes import schedules as sched  # noqa: E402
from popmodel.ingest import uw_bundle, uw_mig, wpp  # noqa: E402
from popmodel import rates  # noqa: E402

END_YEAR = 2150

# Bounds a demographic projection from an eight-billion base cannot leave
# without something being wrong. Deliberately wide: this is an absurdity check,
# not a plausibility opinion.
# Enough levels to reconstruct a readable distribution on the page, rather than
# only a band. The page draws a density from these; it is an interpolation of
# seven known points, not the raw 1,000 draws, and the page says so.
QUANTILE_LEVELS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

WORLD_2100_FLOOR = 3.0e9
WORLD_2100_CEILING = 30.0e9

POST_2100_HOLD = (
    "UW's trajectories end in 2100 and this projection runs to 2150; the final "
    "year's fertility, mortality and sex ratio are held constant thereafter. "
    "This is an assumption of this project, not of the source."
)
POST_2100_CONTINUE = (
    "UW's trajectories end in 2100 and this projection runs to 2150; fertility "
    "and life expectancy are continued by an emulator of the archive's own "
    "2070-2100 behaviour (see popmodel/rates.py), so the source covers every "
    "projected year and no rate is held constant. The continuation is this "
    "project's, not the source's."
)
ZERO_MIGRATION = (
    "zero net migration for every country and year; UW's fertility and "
    "mortality archives carry no migration component and bayesMig was not used"
)


def loc_ids_for(iso3: tuple[str, ...]) -> np.ndarray:
    """UN numeric codes for ISO3 codes, in the order given. Raises on any miss."""
    reference = wpp.load_bundle()
    index = {code: int(loc) for code, loc in zip(reference.iso3, reference.loc_id)}
    missing = [code for code in iso3 if code not in index]
    if missing:
        raise SystemExit(f"no UN code for: {', '.join(missing)}")
    return np.array([index[code] for code in iso3], dtype=np.int64)


def build_base(bundle: uw_bundle.UwDrawBundle):
    """The 1 January 2024 population, restricted to the countries UW models."""
    reference = wpp.load_bundle()
    index = {code: i for i, code in enumerate(reference.iso3)}
    missing = [code for code in bundle.iso3 if code not in index]
    if missing:
        raise SystemExit(f"no WPP base population for: {', '.join(missing)}")
    columns = np.array([index[code] for code in bundle.iso3])

    excluded = sorted(set(reference.iso3) - set(bundle.iso3))
    excluded_people = float(reference.pop_base[[index[c] for c in excluded]].sum())

    base = BasePopulation(
        year=int(reference.years[0]),
        locations=bundle.iso3,
        values=reference.pop_base[columns],
        source_revision=str(reference.provenance["revision_label"]),
        source="WPP 2024 population by single age and sex, 1 January 2024",
    )
    return base, excluded, excluded_people


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--draws", type=int, help="use only the first N trajectories (a quick check)"
    )
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--migration", choices=("uw", "zero"), default="uw",
        help="UW's bayesMig median path, or an explicit zero-migration run",
    )
    parser.add_argument(
        "--post-2100", choices=("continue", "hold"), default="continue",
        help=(
            "continue the source's own late-horizon fertility and longevity "
            "behaviour past 2100 (default), or hold the final rates constant"
        ),
    )
    parser.add_argument(
        "--rate-seed", type=int, default=rates.DEFAULT_SEED,
        help="seed for the post-2100 rate continuation",
    )
    args = parser.parse_args()

    bundle = uw_bundle.load()
    continuation = None
    if args.post_2100 == "continue":
        # Extend the trajectories themselves rather than the age schedules, so
        # every downstream step -- converter, propagator, vintage writer --
        # sees a source that covers the whole horizon and the extension policy
        # never has to invent anything.
        bundle, continuation = rates.extend_bundle(
            bundle, end_year=args.end_year - 1, seed=args.rate_seed
        )
    base, excluded, excluded_people = build_base(bundle)
    print(f"source:    {bundle.provenance['source_label']}")
    print(
        f"draws:     {bundle.n_draws:,} trajectories x {len(bundle.iso3)} locations"
    )
    print(
        f"base:      {base.year}, {base.values.sum() / 1e9:.3f} billion people "
        f"across {len(base.locations)} countries"
    )
    if excluded:
        print(
            f"excluded:  {', '.join(excluded)} - in WPP, absent from UW "
            f"({excluded_people:,.0f} people)"
        )

    post_2100 = POST_2100_CONTINUE if continuation else POST_2100_HOLD
    converter = sched.WppRelationalConverter(
        extension=(
            RateExtensionPolicy.strict() if continuation
            else RateExtensionPolicy.hold_all(POST_2100_HOLD)
        ),
        # The drawn levels now run to the horizon, but the age patterns they are
        # scaled onto still stop in 2100. Reusing the final pattern holds the
        # shape of fertility across ages and the mortality standard, which is a
        # far weaker claim than holding the level and is stated as its own
        # assumption rather than folded into the continuation.
        reference=sched.ReferenceSchedules.from_bundle(
            hold_final_pattern=bool(continuation)
        ),
    )
    if args.migration == "zero":
        migration = MigrationAssumption.zero(
            np.arange(base.year, args.end_year), bundle.iso3
        )
    else:
        source = uw_mig.load()
        # The migration bundle is built over WPP's 237 countries and the draws
        # cover UW's 236, so the composition and the population path are
        # selected down rather than assumed to line up.
        position = {code: i for i, code in enumerate(source.locations)}
        absent = [code for code in bundle.iso3 if code not in position]
        if absent:
            raise SystemExit(
                f"the migration bundle has no composition for: {', '.join(absent)}"
            )
        keep = np.array([position[code] for code in bundle.iso3])
        source = uw_mig.MigrationSource(
            rates=source.rates,
            composition=source.composition[keep],
            locations=bundle.iso3,
            population=source.population[:, keep],
            population_years=source.population_years,
        )
        # Only the years the UN's population path covers. Beyond that the
        # assumption's own hold-last extension takes over, which is recorded
        # on the assumption rather than applied silently here.
        migration = uw_mig.build_assumption(
            source.rates,
            composition=source.composition,
            population=source.population,
            loc_id=loc_ids_for(bundle.iso3),
            locations=bundle.iso3,
            years=source.population_years,
        )
        net = migration.values.sum(axis=(1, 2, 3))
        print(
            f"migration: world net {net.mean() / 1e3:+.1f} thousand a year "
            f"(should be near zero; the rest is the UN's own discrepancy)"
        )
    print(f"migration: {migration.source}")
    if migration.scenario_knob:
        print(f"           scenario knob - {migration.scenario_knob}")
    if continuation:
        print(
            f"post-2100: fertility and longevity continued to {args.end_year} "
            f"by an emulator of the archive's {continuation['fit_years'][0]}-"
            f"{continuation['fit_years'][1]} behaviour"
        )
        clipped = continuation["clipped_share"]
        print(f"           {clipped:.2e} of continued values hit an absurdity rail")
    else:
        print(f"post-2100: rates held constant to {args.end_year}")
    print()

    draws = iter(bundle)
    if args.draws:
        draws = (draw for _, draw in zip(range(args.draws), bundle))

    shifts: list[float] = []
    started = time.time()

    def converted():
        for index, draw in enumerate(draws, start=1):
            projection = converter.convert(draw)
            shifts.append(converter.last_diagnostics.max_abs_shift)
            if index == 1 or index % 25 == 0:
                rate = (time.time() - started) / index
                print(f"  draw {index}: {rate:.2f}s each", flush=True)
            yield projection

    ensemble = propagate(
        base, converted(), end_year=args.end_year, migration=migration
    )
    elapsed = time.time() - started
    print(f"\n{ensemble.n_draws:,} draws projected in {elapsed / 60:.1f} minutes")

    world = ensemble.world / 1e9
    years = ensemble.years
    at_2100 = world[:, int(np.where(years == 2100)[0][0])]
    if at_2100.min() * 1e9 < WORLD_2100_FLOOR or at_2100.max() * 1e9 > WORLD_2100_CEILING:
        raise SystemExit(
            f"the predictive check failed: world population at 2100 spans "
            f"{at_2100.min():.2f}-{at_2100.max():.2f} billion, outside the "
            f"{WORLD_2100_FLOOR / 1e9:.0f}-{WORLD_2100_CEILING / 1e9:.0f} billion "
            f"absurdity bounds. Stop and find out why before trusting anything."
        )

    quantiles = ensemble.quantiles(QUANTILE_LEVELS)
    print("\nworld population, billions")
    print(f"  {'year':>6}  {'5%':>7}  {'50%':>7}  {'95%':>7}")
    for year in (2050, 2075, 2100, 2125, args.end_year):
        if year not in years:
            continue
        i = int(np.where(years == year)[0][0])
        column = quantiles.world[:, i] / 1e9
        low, mid, high = column[0], column[3], column[-1]
        print(f"  {year:>6}  {low:>7.2f}  {mid:>7.2f}  {high:>7.2f}")

    peak_index = np.argmax(quantiles.world[3])
    peak_year = int(years[peak_index])
    print(
        f"\nmedian path peaks at {quantiles.world[3][peak_index] / 1e9:.2f} billion "
        f"in {peak_year}"
    )
    peaks = years[np.argmax(ensemble.world, axis=1)]
    before_2100 = float((peaks < 2100).mean())
    print(f"{before_2100:.1%} of draws peak before 2100")

    receipt = {
        "converter": {"name": converter.name, "version": converter.version},
        "source": bundle.provenance["source_label"],
        "draws": ensemble.n_draws,
        "locations": len(ensemble.locations),
        "excluded_locations": excluded,
        "excluded_people": excluded_people,
        "base_year": base.year,
        "end_year": args.end_year,
        "baseline_character": (
            "UN-equivalent: UW's posterior is mean-reverting, so this band "
            "expresses the conventional long-run assumption, not this project's"
        ),
        "post_2100_assumption": post_2100,
        "post_2100_continuation": continuation,
        "migration": {
            "source": migration.source,
            "independently_sourced": migration.independently_sourced,
            "scenario_knob": migration.scenario_knob,
        },
        "cross_country_pairing": bundle.provenance["cross_country_pairing"],
        "max_abs_mortality_shift": max(shifts),
        "world_billions": {
            str(int(year)): {
                "p05": float(quantiles.world[0, i] / 1e9),
                "p50": float(quantiles.world[3, i] / 1e9),
                "p95": float(quantiles.world[-1, i] / 1e9),
            }
            for i, year in enumerate(years)
        },
        # The peak of the median path, which is what "the median peaks at"
        # means. This field held the MEAN across draws under a name that said
        # median; the two differ by about 0.05 billion here, which is small
        # enough to be quoted for years without anyone noticing.
        "median_peak": {
            "year": peak_year,
            "billions": float(quantiles.world[3, peak_index] / 1e9),
        },
        "mean_at_peak_year": {
            "year": peak_year,
            "billions": float(world[:, peak_index].mean()),  # world is billions
        },
        "share_peaking_before_2100": before_2100,
        "seconds": round(elapsed, 1),
    }
    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = args.output or (paths.OUT / "uw_ensemble.json")
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    # Derived from the receipt's name so two runs cannot overwrite each
    # other's country totals while leaving both JSON files looking fine.
    totals = out.with_name(out.stem + "_country_totals.npz")
    np.savez_compressed(
        totals,
        years=years,
        locations=np.array(ensemble.locations),
        quantile_levels=quantiles.levels,
        location_quantiles=quantiles.locations,
        world=ensemble.world,
    )
    print(f"\nwrote {out}")
    print(f"wrote {totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

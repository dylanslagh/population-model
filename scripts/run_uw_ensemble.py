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

END_YEAR = 2150

# Bounds a demographic projection from an eight-billion base cannot leave
# without something being wrong. Deliberately wide: this is an absurdity check,
# not a plausibility opinion.
WORLD_2100_FLOOR = 3.0e9
WORLD_2100_CEILING = 30.0e9

POST_2100 = (
    "UW's trajectories end in 2100 and this projection runs to 2150; the final "
    "year's fertility, mortality and sex ratio are held constant thereafter. "
    "This is an assumption of this project, not of the source."
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
    args = parser.parse_args()

    bundle = uw_bundle.load()
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

    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.hold_all(POST_2100)
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

    quantiles = ensemble.quantiles((0.05, 0.5, 0.95))
    print("\nworld population, billions")
    print(f"  {'year':>6}  {'5%':>7}  {'50%':>7}  {'95%':>7}")
    for year in (2050, 2075, 2100, 2125, args.end_year):
        if year not in years:
            continue
        i = int(np.where(years == year)[0][0])
        low, mid, high = quantiles.world[:, i] / 1e9
        print(f"  {year:>6}  {low:>7.2f}  {mid:>7.2f}  {high:>7.2f}")

    peak_index = np.argmax(quantiles.world[1])
    peak_year = int(years[peak_index])
    print(
        f"\nmedian path peaks at {quantiles.world[1][peak_index] / 1e9:.2f} billion "
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
        "post_2100_assumption": POST_2100,
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
                "p50": float(quantiles.world[1, i] / 1e9),
                "p95": float(quantiles.world[2, i] / 1e9),
            }
            for i, year in enumerate(years)
        },
        "median_peak": {"year": peak_year, "billions": float(world[:, peak_index].mean())},
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

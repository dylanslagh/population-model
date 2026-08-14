"""Phase 5: run the mechanistic grid and report whether selection catches up.

Spec section 8's two axes. The environment decides how many children a person
of a given disposition has; selection decides how common those dispositions
become; observed fertility is the result of both rather than an input to
either.

The output to read first is **the selection effect**: observed fertility
divided by what the environment alone would have produced. Above one means
composition has pushed fertility above the environment path. The project's
central question is whether and when that happens, and one legitimate answer is
never.

Read the caveat before the numbers
----------------------------------
Seven of thirteen mechanism parameters have been checked against their sources.
Five have no independent support and are explicitly labelled scenario knobs;
the remaining sourced gap is the dispersion of completed family size. The
mechanism is real, but magnitudes remain conditional on those unresolved rows.
Every output file repeats this caveat. See
`docs/mechanism-parameter-audit.md` for the source trail.

    python scripts/run_phase5.py                    # the grid
    python scripts/run_phase5.py --ensemble 200     # with parameter uncertainty
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_to_2150 import _derive_migration  # noqa: E402
from popmodel import paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402
from popmodel.mech import composition, parameters as mech_parameters, runs  # noqa: E402

END_YEAR = 2150
REPORT_YEARS = (2050, 2100, 2150)
WATCH = ("ISR", "USA", "NGA", "KOR", "JPN", "DEU")


def load_inputs():
    bundle = wpp.load_bundle()
    countries = pd.DataFrame({
        "LocID": bundle.loc_id,
        "ISO3_code": bundle.iso3,
        "Location": bundle.name,
    })
    print("Loading the UN medium path to back out migration by age...")
    medium = wpp.medium_population(countries, bundle.years)
    migration = _derive_migration(bundle, medium)
    return bundle, migration


def summarise(result, provenance, parameters) -> dict:
    years = result.years
    world = result.world
    effect = result.selection_effect()
    composition_world = result.world_composition()

    def at(year: int, arr, offset: int = 0):
        index = int(np.where(years == year)[0][0]) - offset
        return arr[index]

    # Population-weighted world selection effect, which is the honest way to
    # aggregate a ratio across countries of wildly different size.
    births = result.births
    weight = births / np.maximum(births.sum(axis=1, keepdims=True), 1e-9)
    world_effect = (effect * weight).sum(axis=1)

    crossing = None
    for index, value in enumerate(world_effect):
        if value > 1.01:  # a one per cent lift, not floating-point noise
            crossing = int(years[index])
            break

    return {
        "key": provenance["key"],
        "world_billions": {
            str(y): float(at(y, world) / 1e9) for y in REPORT_YEARS if y in years
        },
        "peak_year": int(years[int(np.argmax(world))]),
        "peak_billions": float(world.max() / 1e9),
        # Rate years run one short of population years: the last rate year is
        # what produced the final 1 January figure.
        "selection_effect": {
            str(y): float(world_effect[min(int(y - years[0]), len(world_effect) - 1)])
            for y in REPORT_YEARS
        },
        "final_rate_year": int(years[-2]),
        "selection_overtakes_in": crossing,
        "world_selection_effect_final": float(world_effect[-1]),
        "years": [int(y) for y in years],
        "world_path_billions": [float(v / 1e9) for v in world],
        "selection_effect_path": [float(v) for v in world_effect],
        "world_composition_2150": {
            label: float(share)
            for label, share in zip(result.labels, composition_world[-1])
        },
        "watch_countries": {
            iso3: {
                "population_2150_millions": float(
                    at(2150, result.population[:, result.locations.index(iso3)]) / 1e6
                ),
                "selection_effect_2150": float(
                    effect[-1, result.locations.index(iso3)]
                ),
                "composition_2150": {
                    label: float(value)
                    for label, value in zip(
                        result.labels,
                        result.composition[-1, result.locations.index(iso3)],
                    )
                },
            }
            for iso3 in WATCH
            if iso3 in result.locations
        },
        "provenance": provenance,
    }


def print_row(name: str, summary: dict) -> None:
    world = summary["world_billions"]
    effect = summary["selection_effect"]
    crossing = summary["selection_overtakes_in"]
    print(
        f"  {name:<30} {world.get('2050', float('nan')):>6.2f} "
        f"{world.get('2100', float('nan')):>6.2f} {world.get('2150', float('nan')):>6.2f}  "
        f"{effect.get('2100', float('nan')):>7.3f} {effect.get('2150', float('nan')):>7.3f}  "
        f"{crossing if crossing else '   never':>8}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    parser.add_argument(
        "--ensemble", type=int, metavar="N",
        help="also draw N parameter sets from their stated ranges",
    )
    parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args()

    parameters = mech_parameters.load()
    print(f"parameters: {parameters.source_path.name}")
    print(f"  {parameters.caveat()}")
    print()

    shares = composition.toy_demonstration()
    print("Spec 6.6's toy, run rather than asserted (1% group, six children,")
    print("90% retention, mainstream at 1.4):")
    print("  group share after each generation: " + ", ".join(
        f"{s:.1%}" for s in shares
    ))
    print(f"  the spec says 'near 70%'; this arithmetic gives {shares[-1]:.0%}.")
    print("  Not a forecast. A demonstration that retention compounds.")
    print()

    bundle, migration = load_inputs()
    reference_tfr = bundle.asfr.sum(axis=2)

    print(f"\n{'scenario':<32}{'world population, bn':^22}{'selection':^18}{'overtakes':>9}")
    print(f"  {'':<30} {'2050':>6} {'2100':>6} {'2150':>6}  {'2100':>7} {'2150':>7}  {'in':>8}")

    results = {}
    started = time.time()
    for key, scenario in runs.GRID.items():
        result, provenance = runs.run(
            scenario,
            bundle=bundle,
            parameters=parameters,
            reference_tfr=reference_tfr,
            asfr=bundle.asfr,
            sx=bundle.sx,
            srb=bundle.srb,
            migration=migration,
            years=bundle.years,
            end_year=args.end_year,
        )
        summary = summarise(result, provenance, parameters)
        results[key] = summary
        print_row(key, summary)

    print(f"\n  {len(results)} scenarios in {time.time() - started:.0f}s")

    baseline = results["un-equivalent"]["world_billions"].get("2150")
    race = results["race"]["world_billions"].get("2150")
    if baseline and race:
        print(
            f"\n  the race scenario ends {race - baseline:+.2f} billion from the "
            f"UN-equivalent baseline at 2150 ({100 * (race / baseline - 1):+.1f}%)"
        )

    for key, other in runs.INDISTINGUISHABLE.items():
        if key in results and other in results:
            a = results[key]["world_billions"].get("2150")
            b = results[other]["world_billions"].get("2150")
            if a is not None and b is not None and abs(a - b) < 1e-6:
                print(
                    f"  {key} and {other} are numerically identical here, as "
                    f"declared: same environment path, different claimed reason"
                )

    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_year": args.end_year,
        "base_year": int(bundle.years[0]),
        "caveat": parameters.caveat(),
        "parameters": parameters.provenance(),
        "toy_demonstration": {
            "shares_by_generation": shares,
            "note": (
                "spec 6.6's illustration of compounding retention, not a forecast"
            ),
        },
        "migration": (
            "net migrants by age backed out of the UN's own medium path; a "
            "residual, not independent evidence, so every run here is a "
            "diagnostic rather than a test"
        ),
        "scenarios": results,
    }

    if args.ensemble:
        payload["ensemble"] = run_ensemble(
            args.ensemble, bundle, migration, reference_tfr, parameters, args
        )

    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "phase5.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


def run_ensemble(n_draws, bundle, migration, reference_tfr, parameters, args) -> dict:
    """Draw parameters from their stated ranges and rerun the two key scenarios.

    Spec section 6.11: the point of making this uncertain is not decoration. It
    is that almost every mechanism parameter is a range rather than a number,
    and a single central run hides that completely.
    """
    rng = np.random.default_rng(args.seed)
    keys = ("un-equivalent", "race")
    collected = {
        key: {"world_2150": [], "effect_2150": [], "world_paths": [], "effect_paths": []}
        for key in keys
    }

    print(f"\ndrawing {n_draws} parameter sets from their stated ranges")
    started = time.time()
    for draw in range(n_draws):
        sampled = mech_parameters.ParameterSet(
            parameters={
                name: type(p)(
                    name=p.name,
                    value=p.draw(rng) if p.low < p.high else p.value,
                    low=p.low,
                    high=p.high,
                    unit=p.unit,
                    kind=p.kind,
                    verified=p.verified,
                    evidence=p.evidence,
                    provenance=p.provenance,
                    notes=p.notes,
                )
                for name, p in parameters.parameters.items()
            },
            source_path=parameters.source_path,
        )
        for key in keys:
            result, _ = runs.run(
                runs.GRID[key],
                bundle=bundle,
                parameters=sampled,
                reference_tfr=reference_tfr,
                asfr=bundle.asfr,
                sx=bundle.sx,
                srb=bundle.srb,
                migration=migration,
                years=bundle.years,
                end_year=args.end_year,
            )
            births = result.births
            weight = births / np.maximum(births.sum(axis=1, keepdims=True), 1e-9)
            effect = (result.selection_effect() * weight).sum(axis=1)
            collected[key]["world_2150"].append(float(result.world[-1] / 1e9))
            collected[key]["effect_2150"].append(float(effect[-1]))
            collected[key]["world_paths"].append(result.world / 1e9)
            collected[key]["effect_paths"].append(effect)
        if (draw + 1) % 25 == 0:
            print(f"  {draw + 1}/{n_draws}")

    summary = {}
    for key, values in collected.items():
        world = np.array(values["world_2150"])
        effect = np.array(values["effect_2150"])
        summary[key] = {
            "world_2150_billions": {
                "p05": float(np.quantile(world, 0.05)),
                "p50": float(np.quantile(world, 0.50)),
                "p95": float(np.quantile(world, 0.95)),
            },
            "selection_effect_2150": {
                "p05": float(np.quantile(effect, 0.05)),
                "p50": float(np.quantile(effect, 0.50)),
                "p95": float(np.quantile(effect, 0.95)),
            },
            "share_where_selection_overtakes": float((effect > 1.01).mean()),
        }
        paths_world = np.array(values["world_paths"])
        paths_effect = np.array(values["effect_paths"])
        summary[key]["world_band_billions"] = {
            level: np.quantile(paths_world, q, axis=0).tolist()
            for level, q in (("p05", 0.05), ("p50", 0.5), ("p95", 0.95))
        }
        summary[key]["effect_band"] = {
            level: np.quantile(paths_effect, q, axis=0).tolist()
            for level, q in (("p05", 0.05), ("p50", 0.5), ("p95", 0.95))
        }
        print(
            f"  {key}: 2150 world {summary[key]['world_2150_billions']['p05']:.2f}"
            f"-{summary[key]['world_2150_billions']['p95']:.2f} bn, "
            f"selection effect "
            f"{summary[key]['selection_effect_2150']['p05']:.3f}"
            f"-{summary[key]['selection_effect_2150']['p95']:.3f}"
        )
    print(f"  {n_draws} draws in {time.time() - started:.0f}s")
    summary["draws"] = n_draws
    summary["note"] = (
        "parameter uncertainty only: the demographic rates are the UN's medium "
        "path, not the UW posterior"
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())

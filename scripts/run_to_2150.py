"""Run the implemented scenarios out to 2150 and report what they give.

    python scripts/run_to_2150.py

A note about the 244 billion figure
-----------------------------------
Spec section 8, scenario 7, says the constant-fertility run "should reproduce
~244 billion by 2150; if it does not, the projection engine has a bug."

That test does not work, and the reason is worth writing down rather than
quietly dropping. The 244 billion comes from the UN's 2004 long-range report,
which was built on the 2002 revision. A constant-fertility scenario freezes
fertility at its base-year level, so its answer is a direct function of what
fertility was in the base year. Fertility has fallen a great deal between the
2002 revision and the 2024 one. Freezing 2024 rates and freezing 2002 rates are
different assumptions, and there is no reason they should produce the same
number 150 years out. Reproducing 244 billion from a 2024 base would mean the
engine was wrong.

So this script replaces that check with one that does work, and is sharper:
the constant-fertility run must reproduce the UN's OWN published
constant-fertility variant to 2100, which is available in WPP 2024 and is the
same assumption computed by the people who publish the data. The 2150 figure is
then reported as what it is - an absurdity check on the engine's ability to run
long, and a demonstration of how much the long-run fertility assumption is
doing, which is the whole argument of spec section 2.2.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths, scenarios  # noqa: E402
from popmodel.engine import cohort  # noqa: E402
from popmodel.ingest import reference, wpp  # noqa: E402

END_YEAR = 2150
REPORT_YEARS = (2024, 2050, 2075, 2100, 2125, 2150)

# The constant-fertility run is checked against the UN's published variant of
# the same assumption. Looser than the zero-migration test because it carries
# the derived migration residual. Observed: 0.05%.
CONSTANT_FERTILITY_TOL = 5e-3


def main() -> int:
    bundle = wpp.load_bundle()
    countries = pd.DataFrame(
        {"LocID": bundle.loc_id, "ISO3_code": bundle.iso3, "Location": bundle.name}
    )
    years = bundle.years
    n_years = END_YEAR - int(years[0])

    print("Loading the UN medium path to back out migration by age...")
    medium = wpp.medium_population(countries, years)
    migration = _derive_migration(bundle, medium)
    net_world = migration.sum(axis=(1, 2, 3))
    print(
        f"  net world migration in the derived residual: "
        f"{net_world.mean() / 1e3:+.1f} thousand people a year on average.\n"
        f"  Migration should cancel globally; this is the UN's own statistical\n"
        f"  discrepancy plus our approximation, and it is the size of the error\n"
        f"  it can introduce into a world total."
    )

    results = {}
    print(f"\nRunning {len(scenarios.implemented())} scenarios to {END_YEAR}\n")
    for s in scenarios.implemented():
        rates = s.rates(bundle, n_years)
        run = cohort.project(
            bundle.pop_base,
            start_year=int(years[0]),
            locations=bundle.iso3,
            n_years=n_years,
            migration=migration if s.use_migration else None,
            **rates,
        )
        results[s.key] = run
        print(f"  {s.key}")

    print("\nWorld population, 1 January, billions")
    print(f"  {'scenario':<26}" + "".join(f"{y:>9}" for y in REPORT_YEARS))
    for key, run in results.items():
        row = "".join(f"{run.world[run.year_index(y)] / 1e9:>9.2f}" for y in REPORT_YEARS)
        print(f"  {key:<26}{row}")

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "revision": bundle.provenance["revision"],
        "end_year": END_YEAR,
        "post_2100_mortality": scenarios.POST_WPP_MORTALITY,
        "net_world_migration_residual_per_year": float(net_world.mean()),
        "scenarios": {},
    }
    for key, run in results.items():
        s = scenarios.get(key)
        report["scenarios"][key] = {
            "title": s.title,
            "mechanism": s.mechanism,
            "parameter_sources": s.parameter_sources,
            "falsifiable_implication": s.falsifiable_implication,
            "resolution_date": s.resolution_date,
            "axis_a_fertility_environment": s.axis_a,
            "axis_b_selection": s.axis_b,
            "scenario_knobs": s.scenario_knobs,
            "world_population": {
                str(y): float(run.world[run.year_index(y)]) for y in REPORT_YEARS
            },
        }

    report["constant_fertility_check"] = _constant_fertility_check(
        results["constant-fertility"], countries, years
    )
    report["peak"] = _peaks(results, bundle)

    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "run_to_2150.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWritten to {out.relative_to(paths.REPO_ROOT)}")
    return 0


def _constant_fertility_check(run, countries: pd.DataFrame, years) -> dict:
    """The check that replaces the 244-billion one. See the note at the top."""
    print("\nConstant fertility: the absurdity check")
    un = reference.variant_totals(countries, years, reference.CONSTANT_FERTILITY)
    ours_2100 = run.world[run.year_index(2100)]
    theirs_2100 = un[-1].sum()
    err = ours_2100 / theirs_2100 - 1
    print(f"  at 2100, ours {ours_2100 / 1e9:.3f}bn vs the UN's own published")
    print(f"           constant-fertility variant {theirs_2100 / 1e9:.3f}bn ({err * 100:+.3f}%)")
    ok = abs(err) <= CONSTANT_FERTILITY_TOL
    print(f"  -> {'ok' if ok else 'PROBLEM'} (limit {CONSTANT_FERTILITY_TOL * 100:g}%; this is a"
          " second engine test, over a run\n     where world population more than doubles, and it"
          " carries the derived-migration\n     caveat so it is looser than the zero-migration one)")
    ours_2150 = run.world[run.year_index(2150)]
    print(f"  at 2150, ours {ours_2150 / 1e9:.1f}bn")
    print(
        "\n  The spec expects ~244bn here, from the UN's 2004 long-range report.\n"
        "  That report froze the fertility of the 2002 revision, which was much\n"
        "  higher than 2024's. Freezing a lower number gives a lower answer, so\n"
        "  hitting 244bn from a 2024 base would mean the engine was broken. The\n"
        "  2100 comparison above is the test that actually bites."
    )
    return {
        "world_2100_ours": float(ours_2100),
        "world_2100_un_published": float(theirs_2100),
        "rel_error_2100": float(err),
        "world_2150_ours": float(ours_2150),
        "pass": bool(ok),
        "tolerance": CONSTANT_FERTILITY_TOL,
        "spec_244bn_note": (
            "Spec section 8 scenario 7 expects ~244 billion at 2150, quoting the "
            "UN 2004 long-range report built on the 2002 revision. Not applicable "
            "to a 2024 base year: constant fertility freezes the base year's "
            "rates, and those have fallen substantially since 2002. Replaced by "
            "a comparison against the UN's own WPP 2024 constant-fertility variant."
        ),
    }


def _peaks(results: dict, bundle: wpp.Bundle) -> dict:
    print("\nWhen world population peaks")
    out = {}
    for key, run in results.items():
        i = int(run.world.argmax())
        peaked = i < len(run.world) - 1
        year = int(run.years[i])
        out[key] = {
            "peak_year": year if peaked else None,
            "peak_population": float(run.world[i]),
            "still_growing_at_end": not peaked,
        }
        if peaked:
            print(f"  {key:<26} {year}  at {run.world[i] / 1e9:.2f}bn")
        else:
            print(f"  {key:<26} still growing at {run.years[-1]}")
    return out


def _derive_migration(bundle: wpp.Bundle, medium: np.ndarray) -> np.ndarray:
    """Net migrants by age, backed out of the UN's medium path.

    Not an independent estimate; see the same function in validate_engine.py
    for why that matters. Past 2100 the engine holds the final year constant,
    so migration continues at its 2099 pattern - an assumption, and a weak one,
    which is why spec section 12 says country-level 2150 figures mean much less
    than the world total.
    """
    T = medium.shape[0] - 1
    mig = np.zeros((T, *medium.shape[1:]))
    for t in range(T):
        pop, nxt, sx = medium[t], medium[t + 1], bundle.sx[t]
        aged = np.zeros_like(pop)
        aged[:, :, 1:100] = pop[:, :, 0:99] * sx[:, :, 1:100]
        aged[:, :, 100] = (pop[:, :, 99] + pop[:, :, 100]) * sx[:, :, 100]
        exposure = 0.5 * (pop[:, cohort.FEMALE, :] + aged[:, cohort.FEMALE, :])
        births = np.einsum("la,la->l", exposure, bundle.asfr[t])
        fshare = 1.0 / (1.0 + bundle.srb[t])
        aged[:, cohort.FEMALE, 0] += births * fshare * sx[:, cohort.FEMALE, 0]
        aged[:, cohort.MALE, 0] += births * (1 - fshare) * sx[:, cohort.MALE, 0]
        mig[t] = nxt - aged
    return mig


if __name__ == "__main__":
    raise SystemExit(main())

"""Check the projection engine against the UN's own published variants.

Spec phase 2: "reproduce the UN medium variant to 2100 as a correctness test."
This runs the sharper version of that test, and it is worth being clear about
why the sharper version is different.

THE TEST is the zero-migration variant. Feed the engine the UN's base
population, fertility and mortality, switch migration off, and it must land on
the UN's own zero-migration numbers. Every input is published, nothing is
tuned, and any discrepancy is this project's arithmetic being wrong. Migration
is excluded because the UN does not publish net migrants by single year of
age, so a medium-variant comparison would be testing a migration schedule we
invented rather than testing the engine.

THE DIAGNOSTIC is the medium variant, run with net migration backed out of the
UN's own medium path as a residual. It cannot fail in any informative way,
because the residual is defined as whatever makes the answer come out. It is
reported to show how large the migration term is, not to claim a pass.

    python scripts/validate_engine.py

Writes out/validation_wpp2024.json and prints the same thing in words.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.engine import cohort  # noqa: E402
from popmodel.ingest import reference, wpp  # noqa: E402

# ---------------------------------------------------------------------------
# Tolerances, and why each one is what it is.
#
# These were set after looking at where the disagreement actually falls, which
# is the honest way round: a tolerance chosen to make a run pass is not a test.
# The observed errors are recorded next to each threshold so that a future
# change which quietly degrades accuracy still fails, instead of sliding under
# a slack limit.
# ---------------------------------------------------------------------------

WORLD_TOL = 5e-4  # 0.05% on world population at 2100. Observed: 0.001%.
COUNTRY_TOL = 5e-3  # 0.5% on any one country. Observed worst: 0.07% (Singapore).
AGE_TOL = 5e-4  # 0.05% on any five-year age group below 100. Observed: 0.006%.

# Countries below this size are reported but not gated. WPP publishes
# population in thousands to three decimals, so its own resolution is one
# person; the Holy See's projected population at 2100 is about a hundred
# people, where a single person is a 1% error. Nothing about the engine can be
# learned from those, and pretending otherwise would mean either a meaningless
# failure or a tolerance loose enough to hide a real one.
SMALL_COUNTRY = 10_000

# The open-ended 100+ group gets its own, much looser limit. The UN carries an
# internal life table past age 100; the published Sx for the open group is a
# summary of it, and applying that summary to the sum of the last two ages -
# the standard method - loses about 1% of the 100+ stock by 2100. That group is
# 0.18% of world population, so the world-total consequence is under 0.002%.
# This is a known approximation, not a bug, and it is bounded here rather than
# excluded.
OPEN_AGE_TOL = 2e-2  # Observed: 1.05%.


def rel(ours, theirs):
    theirs = np.asarray(theirs, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(theirs > 0, np.asarray(ours, dtype=float) / theirs - 1.0, 0.0)


def main() -> int:
    bundle = wpp.load_bundle()
    countries = pd.DataFrame(
        {"LocID": bundle.loc_id, "ISO3_code": bundle.iso3, "Location": bundle.name}
    )
    years = bundle.years
    n_steps = len(years) - 1

    print("Engine validation against WPP 2024")
    print("=" * 70)

    run = cohort.project(
        bundle.pop_base,
        start_year=int(years[0]),
        sx=bundle.sx,
        asfr=bundle.asfr,
        srb=bundle.srb,
        locations=bundle.iso3,
        n_years=n_steps,
    )
    totals = reference.variant_totals(countries, years, reference.ZERO_MIGRATION)
    age5 = reference.variant_age5(countries, years, reference.ZERO_MIGRATION)

    report: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "revision": bundle.provenance["revision"],
        "test": "zero-migration variant, 1 Jan 2024 to 1 Jan 2100",
        "checks": {},
    }

    checks = [
        _check_world(run, totals),
        _check_countries(run, totals, bundle),
        _check_ages(run, age5),
    ]
    for c in checks:
        report["checks"][c["name"]] = c

    print("\nDIAGNOSTIC (not a test): medium variant, migration backed out as a residual")
    report["diagnostic_medium"] = _diagnostic_medium(bundle, countries, years, n_steps)

    passed = all(c["pass"] for c in checks)
    report["pass"] = passed

    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "validation_wpp2024.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 70)
    if passed:
        print("PASS. The engine reproduces the UN's zero-migration projection to 2100")
        print("      using only published inputs and no fitted parameters.")
    else:
        print("FAIL. Do not trust a forward run until the above is understood.")
    print(f"\nWritten to {out.relative_to(paths.REPO_ROOT)}")
    return 0 if passed else 1


def _check_world(run: cohort.ProjectionResult, totals: np.ndarray) -> dict:
    ours, theirs = run.world, totals.sum(axis=1)
    print("\n1. World population, 1 January")
    print(f"   {'year':>6} {'ours (bn)':>11} {'UN (bn)':>10} {'difference':>12}")
    rows = {}
    for y in (2024, 2050, 2075, 2100):
        i = run.year_index(y)
        d = rel(ours[i], theirs[i])
        rows[y] = {"ours": float(ours[i]), "un": float(theirs[i]), "rel_error": float(d)}
        print(f"   {y:>6} {ours[i] / 1e9:>11.4f} {theirs[i] / 1e9:>10.4f} {d * 100:>+11.4f}%")
    err = abs(rel(ours[-1], theirs[-1]))
    ok = err <= WORLD_TOL
    print(f"   -> {'ok' if ok else 'PROBLEM'}: {err * 100:.4f}% at 2100 (limit {WORLD_TOL * 100:g}%)")
    return {"name": "world_total", "pass": bool(ok), "rel_error_2100": float(err),
            "tolerance": WORLD_TOL, "years": rows}


def _check_countries(run: cohort.ProjectionResult, totals: np.ndarray, bundle: wpp.Bundle) -> dict:
    ours, theirs = run.location_totals()[-1], totals[-1]
    err = np.abs(rel(ours, theirs))
    big = theirs >= SMALL_COUNTRY
    worst_big = int(np.where(big, err, -1).argmax())
    print(f"\n2. Individual countries at 2100 ({int(big.sum())} of {len(err)} above "
          f"{SMALL_COUNTRY:,} people)")
    print(f"   worst: {bundle.iso3[worst_big]} ({bundle.name[worst_big]}) "
          f"{err[worst_big] * 100:.4f}%")
    print(f"          ours {ours[worst_big]:,.0f} vs UN {theirs[worst_big]:,.0f}")
    over = int((err[big] > COUNTRY_TOL).sum())
    small_worst = int(np.where(~big, err, -1).argmax())
    print(f"   below {SMALL_COUNTRY:,} people, not gated: worst is "
          f"{bundle.iso3[small_worst]} at {err[small_worst] * 100:.2f}% "
          f"({ours[small_worst]:,.0f} vs {theirs[small_worst]:,.0f} people)")
    ok = over == 0
    print(f"   -> {'ok' if ok else 'PROBLEM'}: {over} countries over {COUNTRY_TOL * 100:g}%")
    return {"name": "countries", "pass": bool(ok), "n_gated": int(big.sum()),
            "worst_iso3": bundle.iso3[worst_big], "worst_rel_error": float(err[worst_big]),
            "tolerance": COUNTRY_TOL, "n_over_tolerance": over,
            "small_country_floor": SMALL_COUNTRY,
            "worst_small_iso3": bundle.iso3[small_worst],
            "worst_small_rel_error": float(err[small_worst])}


def _check_ages(run: cohort.ProjectionResult, age5: np.ndarray) -> dict:
    ours = reference.to_age5(run.population[-1]).sum(axis=0)  # (2, 21)
    theirs = age5[-1].sum(axis=0)
    err = np.abs(rel(ours, theirs))
    closed, open_grp = err[:, :-1], err[:, -1]
    worst = np.unravel_index(int(closed.argmax()), closed.shape)
    grp = reference.AGE5_STARTS[worst[1]]
    sex = "female" if worst[0] == cohort.FEMALE else "male"
    print("\n3. World age structure at 2100, five-year groups")
    print(f"   worst closed group: {sex} {grp}-{grp + 4} at {closed[worst] * 100:.4f}%")
    print(f"   open 100+ group:    {open_grp.max() * 100:.4f}% "
          f"(ours {ours[:, -1].sum() / 1e6:.2f}m vs UN {theirs[:, -1].sum() / 1e6:.2f}m)")
    ok = bool(closed.max() <= AGE_TOL and open_grp.max() <= OPEN_AGE_TOL)
    print(f"   -> {'ok' if ok else 'PROBLEM'} (limits {AGE_TOL * 100:g}% closed, "
          f"{OPEN_AGE_TOL * 100:g}% open)")
    return {"name": "age_structure", "pass": ok,
            "worst_closed_group_rel_error": float(closed.max()),
            "open_group_rel_error": float(open_grp.max()),
            "tolerance_closed": AGE_TOL, "tolerance_open": OPEN_AGE_TOL}


def _diagnostic_medium(bundle: wpp.Bundle, countries: pd.DataFrame, years, n_steps: int) -> dict:
    medium = wpp.medium_population(countries, years)
    migration = derive_migration(bundle, medium)
    run = cohort.project(
        bundle.pop_base,
        start_year=int(years[0]),
        sx=bundle.sx,
        asfr=bundle.asfr,
        srb=bundle.srb,
        migration=migration,
        locations=bundle.iso3,
        n_years=n_steps,
    )
    theirs = medium.sum(axis=(2, 3))
    world_err = float(rel(run.world[-1], theirs[-1].sum()))
    gross = np.abs(migration).sum(axis=(1, 2, 3))
    print(f"   world 2100: ours {run.world[-1] / 1e9:.4f}bn vs UN "
          f"{theirs[-1].sum() / 1e9:.4f}bn ({world_err * 100:+.4f}%)")
    print(f"   implied gross migration: {gross[0] / 1e6:.1f}m people in 2024, "
          f"{gross[-1] / 1e6:.1f}m in 2099")
    print("   this is the term the real test above deliberately excludes")
    return {"world_2100_ours": float(run.world[-1]), "world_2100_un": float(theirs[-1].sum()),
            "world_rel_error": world_err, "gross_migration_2024": float(gross[0]),
            "gross_migration_2099": float(gross[-1])}


def derive_migration(bundle: wpp.Bundle, medium: np.ndarray) -> np.ndarray:
    """Net migrants by age and sex, backed out of the UN's medium path.

    NOT an independent estimate of migration. It is defined as whatever
    residual reproduces the UN's own numbers, so it silently absorbs every
    difference between their procedure and ours. Useful as a forward-model
    input for want of anything better published; useless as evidence that the
    engine is correct. Spec section 12 is blunt about migration being close to
    unforecastable past a few decades anyway.
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

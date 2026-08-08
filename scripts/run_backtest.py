"""Mark thirty years of UN population projections against what actually happened.

    python scripts/run_backtest.py

Writes out/backtest.json and out/backtest_*.csv, and prints the results in
words. See src/popmodel/backtest.py for what is being measured and the two
things that would be dishonest to leave out of the summary.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import backtest, paths  # noqa: E402
from popmodel.sources import wpp_archive  # noqa: E402


def main() -> int:
    paths.OUT.mkdir(parents=True, exist_ok=True)
    print("Backtest: every WPP revision 1992-2008, graded against WPP 2024")
    print("=" * 72)

    pop = backtest.grade_all("population")
    tfr = backtest.grade_all("tfr")
    e0 = backtest.grade_all("life_expectancy")
    for name, df in (("population", pop), ("tfr", tfr), ("life_expectancy", e0)):
        df.to_csv(paths.OUT / f"backtest_{name}.csv", index=False)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graded_against": "UN WPP 2024 estimates (a model output, not ground truth)",
        "vintages": sorted(pop.vintage.unique().tolist()),
        "locations": backtest.REPORT_LOCATIONS,
    }

    report["world_population"] = _world_population(pop)
    report["by_horizon"] = _horizon(pop)
    report["regions"] = _regions(pop)
    report["fertility"] = _fertility(tfr)
    report["life_expectancy"] = _life_expectancy(e0)
    report["interval_coverage"] = _coverage()

    out = paths.OUT / "backtest.json"
    out.write_text(json.dumps(report, indent=2, default=_jsonable) + "\n", encoding="utf-8")
    print(f"\nWritten to {out.relative_to(paths.REPO_ROOT)} and backtest_*.csv")
    return 0


def _world_population(pop: pd.DataFrame) -> dict:
    print("\n1. World population: what each vintage said, and what happened")
    w = pop[pop.loc_id == 900]
    target = 2020
    rows = {}
    print(f"   projections for {target}, and for the latest year each vintage can be graded on\n")
    print(f"   {'vintage':>8} {'for 2020':>12} {'actual':>10} {'error':>9}   {'longest graded':>28}")
    for v in sorted(w.vintage.unique()):
        sub = w[w.vintage == v]
        at = sub[sub.period_start == target]
        last = sub.loc[sub.period_start.idxmax()]
        cell = "-"
        if len(at):
            r = at.iloc[0]
            cell = f"{r.projected / 1e9:.3f}bn  {r.actual / 1e9:.3f}bn {r.rel_error * 100:+7.2f}%"
            rows[int(v)] = {"target": target, "projected": float(r.projected),
                            "actual": float(r.actual), "rel_error": float(r.rel_error)}
        print(f"   {int(v):>8}   {cell:<34}"
              f"{int(last.period_start)} ({int(last.horizon)}yr): {last.rel_error * 100:+.2f}%")
    signed = w.rel_error.mean()
    print(f"\n   Across every vintage and every graded year, the mean signed error is "
          f"{signed * 100:+.2f}%.")
    print("   The sign is the interesting part: a systematic direction is a bias, not noise.")
    return {"per_vintage_2020": rows, "mean_signed_error_all": float(signed),
            "mean_absolute_error_all": float(np.abs(w.rel_error).mean())}


def _horizon(pop: pd.DataFrame) -> dict:
    print("\n2. Error against how far ahead the forecast was looking (world)")
    h = backtest.by_horizon(pop)
    print(f"   {'horizon':>10} {'n':>4} {'mean signed':>13} {'mean absolute':>15} {'worst':>9}")
    for _, r in h.iterrows():
        print(f"   {str(r.bucket):>10} {int(r.n):>4} {r.mean_signed * 100:>+12.2f}% "
              f"{r.mean_absolute * 100:>14.2f}% {r.worst * 100:>+8.2f}%")
    return h.assign(bucket=h.bucket.astype(str)).to_dict("records")


def _regions(pop: pd.DataFrame) -> dict:
    print("\n3. Which regions the errors came from (mean signed error, all vintages)")
    g = pop[pop.loc_id != 900].groupby("location").rel_error.agg(["size", "mean"])
    g = g.sort_values("mean")
    print(f"   {'region':>34} {'n':>4} {'mean signed error':>19}")
    for name, r in g.iterrows():
        print(f"   {name:>34} {int(r['size']):>4} {r['mean'] * 100:>+18.2f}%")
    print("\n   Negative means the UN projected fewer people than turned out to be there.")
    return {str(k): {"n": int(v["size"]), "mean_signed": float(v["mean"])} for k, v in g.iterrows()}


def _fertility(tfr: pd.DataFrame) -> dict:
    print("\n4. Fertility: the spec predicts two specific failures")
    out = {}
    for loc, label, expectation in (
        (903, "Africa", "expected: decline projected too fast, so fertility under-projected"),
        (906, "Eastern Asia", "expected: floor assumed near replacement, so over-projected"),
    ):
        sub = tfr[tfr.loc_id == loc]
        if sub.empty:
            print(f"   {label}: no gradeable data")
            continue
        m = sub.rel_error.mean()
        worst = sub.loc[sub.rel_error.abs().idxmax()]
        print(f"   {label:>14}: mean {m * 100:+.1f}%  "
              f"(worst: WPP{int(worst.vintage)} said {worst.projected:.2f} for "
              f"{int(worst.period_start)}-{int(worst.period_end)}, actual {worst.actual:.2f})")
        print(f"   {'':>14}  {expectation}")
        out[label] = {"mean_signed": float(m), "n": int(len(sub)),
                      "worst_vintage": int(worst.vintage),
                      "worst_projected": float(worst.projected),
                      "worst_actual": float(worst.actual)}
    world = tfr[tfr.loc_id == 900]
    print(f"   {'World':>14}: mean {world.rel_error.mean() * 100:+.1f}%")
    out["World"] = {"mean_signed": float(world.rel_error.mean()), "n": int(len(world))}
    return out


def _life_expectancy(e0: pd.DataFrame) -> dict:
    print("\n5. Life expectancy: the spec predicts sixty years of under-projection")
    w = e0[e0.loc_id == 900]
    m = w.abs_error.mean()
    print(f"   World: mean error {m:+.2f} years across {len(w)} graded periods "
          f"({w.rel_error.mean() * 100:+.2f}%)")
    print("   A negative number means the UN expected people to die younger than they did.")
    per = w.groupby("vintage").abs_error.mean()
    for v, e in per.items():
        print(f"     WPP{int(v)}: {e:+.2f} years")
    return {"world_mean_years": float(m),
            "per_vintage_years": {int(k): float(v) for k, v in per.items()}}


def _coverage() -> dict:
    print("\n6. Did reality stay inside the low-to-high band? (world)")
    frames = [backtest.interval_coverage(k) for k in wpp_archive.DEFAULT_KEYS]
    frames = [f for f in frames if len(f)]
    cov = pd.concat(frames, ignore_index=True)
    w = cov[cov.loc_id == 900]
    rate = w.inside.mean()
    print(f"   {int(w.inside.sum())} of {len(w)} world-level projections landed inside "
          f"the band ({rate * 100:.0f}%).")
    outside = w[~w.inside]
    if len(outside):
        r = outside.loc[outside.period_start.idxmax()]
        print(f"   Example miss: WPP{int(r.vintage)} for {int(r.period_start)} gave "
              f"{r.low / 1e9:.2f}-{r.high / 1e9:.2f}bn; actual {r.actual / 1e9:.2f}bn.")
    print("   These are fertility scenarios, not a probability interval, so this is")
    print("   'was reality inside the printed range', not a calibration score.")
    cov.to_csv(paths.OUT / "backtest_coverage.csv", index=False)
    return {"world_inside": int(w.inside.sum()), "world_total": int(len(w)),
            "world_rate": float(rate)}


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    raise SystemExit(main())

"""Store a dated, immutable record of what the model currently says.

    python scripts/write_vintage.py

Reads out/run_to_2150.json and out/validation_wpp2024.json, so run those first.

A note on what this first vintage does and does not contain. At phase 2 the
project has an engine and no mechanism of its own, so every number below is a
reproduction of the UN's assumptions carried forward, not a claim this project
is making. They are all flagged `is_project_claim: false`. Scoring them later
as if they were the project's predictions would credit or blame it for someone
else's model.

There is also nothing here that resolves soon. Spec section 11 is clear that
the first real grade is completed cohort fertility for the early-1990s birth
cohorts, around 2038, and this project has nothing to say about that yet.
Recording an empty scoreboard honestly is better than inventing something to
put on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402
from popmodel.track import vintage  # noqa: E402

NOT_OURS = (
    "Not this project's claim. The engine run uses the UN's own fertility and "
    "mortality assumptions unchanged; only the arithmetic is ours. Recorded as "
    "a baseline, and to exercise the storage format."
)
DETERMINISTIC = (
    "A point, not a distribution: the engine is deterministic and the Bayesian "
    "layer is phase 4. Cannot be scored with a proper rule until it has an "
    "uncertainty attached."
)


def main() -> int:
    run = _load("run_to_2150.json")
    val = _load("validation_wpp2024.json")
    bundle_meta = json.loads((wpp.bundle_path().with_suffix(".json")).read_text(encoding="utf-8"))

    med = run["scenarios"]["un-medium"]
    const = run["constant_fertility_check"]
    peak = run["peak"]["un-medium"]

    v = vintage.new_vintage(
        "phase2-engine",
        "Phase 2: deterministic engine, UN assumptions carried to 2150",
        model_name="popmodel deterministic cohort-component engine",
        model_phase=2,
        data_provenance=bundle_meta,
        notes=(
            "First stored vintage. Contains no claim of this project's own: the "
            "mechanistic layer (spec section 6) is not built. Its purpose is to "
            "fix the file format early, as spec section 10 asks, and to record "
            "the engine's validation state at the moment the numbers below were "
            "produced. Engine validation: world population at 2100 within "
            f"{val['checks']['world_total']['rel_error_2100'] * 100:.4f}% of the "
            "UN's published zero-migration variant."
        ),
    )

    v.quantities += [
        vintage.Quantity(
            id="world_population_2100_un_medium",
            description=(
                "World population on 1 January 2100, running the UN's medium "
                "fertility and mortality assumptions through this engine, with "
                "net migration backed out of the UN's own medium path."
            ),
            unit="people",
            resolution_date="2100",
            source_of_truth="UN WPP estimates for 2100, or successor series",
            is_project_claim=False,
            kind="point",
            point=med["world_population"]["2100"],
            scenario="un-medium",
            notes=f"{NOT_OURS} {DETERMINISTIC}",
        ),
        vintage.Quantity(
            id="world_population_2150_un_medium",
            description=(
                "World population on 1 January 2150 under the same assumptions, "
                "with fertility and mortality held at their 2100 levels beyond "
                "the end of the published series."
            ),
            unit="people",
            resolution_date="2150",
            source_of_truth="UN WPP estimates for 2150, or successor series",
            is_project_claim=False,
            kind="point",
            point=med["world_population"]["2150"],
            scenario="un-medium",
            notes=(
                f"{NOT_OURS} {DETERMINISTIC} Holding mortality flat after 2100 is "
                "an assumption and probably a conservative one: spec section 10 "
                "records that life expectancy gains have been under-projected for "
                "sixty years running."
            ),
        ),
        vintage.Quantity(
            id="world_population_peak_year_un_medium",
            description="Calendar year in which world population peaks, UN medium assumptions.",
            unit="year",
            resolution_date="~2090, once the peak is behind us",
            source_of_truth="UN WPP estimates, or successor series",
            is_project_claim=False,
            kind="point",
            point=float(peak["peak_year"]),
            scenario="un-medium",
            notes=f"{NOT_OURS} {DETERMINISTIC}",
        ),
        vintage.Quantity(
            id="world_population_2150_constant_fertility",
            description=(
                "World population on 1 January 2150 if every woman kept bearing "
                "children at the UN's frozen constant-fertility rates forever."
            ),
            unit="people",
            resolution_date="never - this is a check, not a forecast",
            source_of_truth="n/a; the assumption is known to be false",
            is_project_claim=False,
            kind="point",
            point=const["world_2150_ours"],
            scenario="constant-fertility",
            notes=(
                "Absurdity check. Recorded because the size of the gap between "
                "this and the medium run is the whole argument of spec section "
                "2.2: the long-run fertility process is doing essentially all "
                "the work. Validated against the UN's own constant-fertility "
                f"variant at 2100, {const['rel_error_2100'] * 100:+.3f}%."
            ),
        ),
    ]

    try:
        d = vintage.write(v)
    except vintage.VintageExists as exc:
        print(f"Nothing written.\n\n{exc}")
        return 1
    print(f"Wrote {d.relative_to(paths.REPO_ROOT)}")
    for q in v.quantities:
        val_str = f"{q.point:,.0f}" if q.point and q.point > 1e4 else f"{q.point:g}"
        print(f"  {q.id:<44} {val_str}")
    print("\nNone of these are this project's own claims. See the vintage notes.")
    print("Verify at any time with: python scripts/write_vintage.py --verify")
    return 0


def _load(name: str) -> dict:
    p = paths.OUT / name
    if not p.exists():
        raise SystemExit(
            f"{p} is missing. Run scripts/validate_engine.py and scripts/run_to_2150.py first."
        )
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    if "--verify" in sys.argv:
        results = vintage.verify_all()
        if not results:
            print("No vintages stored yet.")
        for name, ok in results:
            print(f"  {'ok      ' if ok else 'TAMPERED'}  {name}")
        raise SystemExit(0 if all(ok for _, ok in results) else 1)
    raise SystemExit(main())

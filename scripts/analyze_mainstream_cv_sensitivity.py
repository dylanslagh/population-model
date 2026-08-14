"""Propagate the empirical completed-family-size CV through Phase 5.

The four declared values are the empirical low, selected center, superseded
center, and empirical high.  This is a sensitivity analysis, not a fit: none of
the values is chosen from the population projection it produces.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_phase5
from popmodel import paths
from popmodel.ingest import wpp
from popmodel.mech import parameters as mech_parameters
from popmodel.mech import runs


VALUES = (0.44, 0.57, 0.60, 0.80)
SCENARIOS = (
    "mainstream-only",
    "full-selection-un-environment",
    "race",
)
OUT = paths.REFERENCE / "mainstream_propensity_cv_sensitivity.json"


def with_cv(parameters: mech_parameters.ParameterSet, value: float):
    changed = dict(parameters.parameters)
    changed["mainstream_propensity_cv"] = replace(
        changed["mainstream_propensity_cv"], value=value
    )
    return mech_parameters.ParameterSet(changed, parameters.source_path)


def main() -> None:
    base = mech_parameters.load()
    bundle, migration = run_phase5.load_inputs()
    reference_tfr = bundle.asfr.sum(axis=2)
    rows = []
    for value in VALUES:
        parameters = with_cv(base, value)
        for key in SCENARIOS:
            result, provenance = runs.run(
                runs.GRID[key],
                bundle=bundle,
                parameters=parameters,
                reference_tfr=reference_tfr,
                asfr=bundle.asfr,
                sx=bundle.sx,
                srb=bundle.srb,
                migration=migration,
                years=bundle.years,
                end_year=2150,
            )
            summary = run_phase5.summarise(result, provenance, parameters)
            rows.append(
                {
                    "cv": value,
                    "scenario": key,
                    "world_2150_billions": summary["world_billions"]["2150"],
                    "selection_effect_2150": summary["selection_effect"]["2150"],
                    "peak_year": summary["peak_year"],
                    "peak_billions": summary["peak_billions"],
                }
            )

    payload = {
        "generated": "2026-08-13",
        "parameter": "mainstream_propensity_cv",
        "values": list(VALUES),
        "scenarios": list(SCENARIOS),
        "interpretation": (
            "0.44 and 0.80 bound the observed low-fertility country range; "
            "0.57 is its median and 0.60 is the superseded assumption."
        ),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(
            f"CV {row['cv']:.2f}  {row['scenario']:<31s} "
            f"2150 {row['world_2150_billions']:.3f}bn  "
            f"selection {row['selection_effect_2150']:.3f}"
        )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

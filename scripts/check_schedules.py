"""The Phase 4 step-4 checkpoint: prove the schedule converter before it scales.

The converter turns one fertility number and two mortality numbers per country
per year into the hundred-odd rates the engine needs. This script takes every
exported UW country available, converts all 1,000 trajectories, and checks that
what comes out reproduces what went in.

Two things are being verified, and they are different in kind:

* **Reconstruction.** The converted schedules must reproduce the drawn total
  fertility rate and the drawn female and male life expectancies. This is a
  correctness check with a declared tolerance, and it either passes or the run
  stops.
* **How hard the assumption is working.** The converter borrows the UN's age
  patterns and moves only their level. The size of that move is reported, not
  asserted, because there is no threshold at which it becomes wrong -- only a
  point past which the borrowed age pattern is carrying a claim of its own.

Nothing here is fitted and nothing is tuned. Run it before exporting the other
234 locations.

    python scripts/check_schedules.py
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
from popmodel.bayes import RateExtensionPolicy  # noqa: E402
from popmodel.bayes import schedules as sched  # noqa: E402
from popmodel.ingest import uw  # noqa: E402

# Declared tolerances. Fertility is exact by construction -- rescaling a set of
# rates to a new sum reproduces that sum -- so it is held to floating point.
# Life expectancy is solved numerically, and a millionth of a year is roughly
# thirty seconds.
TFR_TOLERANCE = 1e-10
E0_TOLERANCE_YEARS = 1e-6

EXPORT_ROOT = paths.INTERIM / "UW_WPP2024" / "exports"


def check_export(directory: Path, converter: sched.WppRelationalConverter) -> dict:
    """Convert every trajectory in one country's export and grade the result."""
    export = uw.validate_uw_export(directory)

    worst_tfr = 0.0
    worst_e0 = 0.0
    max_shift = 0.0
    shift_sum = 0.0
    large_shift_share = 0.0
    min_ratio = np.inf
    max_ratio = 0.0
    n = 0

    started = time.time()
    for draw in export:
        projection = converter.convert(draw)

        worst_tfr = max(
            worst_tfr, float(np.abs(projection.asfr.sum(axis=-1) - draw.tfr).max())
        )
        produced = sched.life_expectancy(projection.sx)
        wanted = np.stack([draw.e0_female, draw.e0_male], axis=-1)
        worst_e0 = max(worst_e0, float(np.abs(produced - wanted).max()))

        d = converter.last_diagnostics
        max_shift = max(max_shift, d.max_abs_shift)
        shift_sum += d.mean_abs_shift
        large_shift_share += d.share_above_large_shift
        min_ratio = min(min_ratio, d.min_fertility_ratio)
        max_ratio = max(max_ratio, d.max_fertility_ratio)
        n += 1

    if n != len(export):
        raise SystemExit(f"{directory.name}: converted {n} of {len(export)} trajectories")

    elapsed = time.time() - started
    result = {
        "country": export.country,
        "iso3": export.iso3,
        "loc_id": export.loc_id,
        "trajectories": n,
        "seconds": round(elapsed, 2),
        "worst_tfr_error": worst_tfr,
        "worst_e0_error_years": worst_e0,
        "tfr_tolerance": TFR_TOLERANCE,
        "e0_tolerance_years": E0_TOLERANCE_YEARS,
        "max_abs_shift": max_shift,
        "mean_abs_shift": shift_sum / n,
        "share_above_large_shift": large_shift_share / n,
        "fertility_scale_range": [min_ratio, max_ratio],
        "passed": worst_tfr <= TFR_TOLERANCE and worst_e0 <= E0_TOLERANCE_YEARS,
    }

    verdict = "ok  " if result["passed"] else "FAIL"
    print(
        f"  {verdict} {export.country} ({export.iso3}): {n:,} trajectories in "
        f"{elapsed:.1f}s"
    )
    print(
        f"       reconstruction  TFR {worst_tfr:.2e}  "
        f"e0 {worst_e0:.2e} years"
    )
    print(
        f"       level shift     max {max_shift:.3f}  mean "
        f"{result['mean_abs_shift']:.3f}  "
        f"{result['share_above_large_shift']:.2%} above {sched.LARGE_SHIFT}"
    )
    print(
        f"       fertility scaled {min_ratio:.3f}-{max_ratio:.3f}x the UN's own rate"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--exports", type=Path, default=EXPORT_ROOT, help="directory of country exports"
    )
    args = parser.parse_args()

    directories = sorted(d for d in args.exports.glob("*") if d.is_dir())
    if not directories:
        raise SystemExit(
            f"no country exports under {args.exports}\n"
            f"  Run:  python scripts/export_uw_fixture.py --rscript <Rscript.exe>"
        )

    converter = sched.WppRelationalConverter(
        # This script only converts rates; it does not project, so no year past
        # the source is ever reached. Requiring the source to cover every year
        # is the honest setting for a conversion check.
        extension=RateExtensionPolicy.strict(),
    )
    print(f"converter: {converter.name} {converter.version}")
    print(f"reference: {converter.reference.revision}")
    print(f"exports:   {len(directories)} country/countries under {args.exports}")
    print()

    results = [check_export(directory, converter) for directory in directories]
    print()

    receipt = {
        "converter": {"name": converter.name, "version": converter.version},
        "reference_revision": converter.reference.revision,
        "rate_conversion": converter.rate_conversion,
        "tolerances": {
            "tfr": TFR_TOLERANCE,
            "e0_years": E0_TOLERANCE_YEARS,
        },
        "countries": results,
    }
    paths.OUT.mkdir(parents=True, exist_ok=True)
    out = paths.OUT / "schedule_check.json"
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"FAILED for {len(failed)} country/countries; wrote {out}")
        return 1
    print(f"all {len(results)} country export(s) reconstruct their source draws")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

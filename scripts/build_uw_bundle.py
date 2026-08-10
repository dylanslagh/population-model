"""Compact the 236 validated UW country exports into one array bundle.

The CSV exports stay the evidence. This is the convenient form: one file the
ensemble run can open once instead of parsing 18 million rows on every run.
Every export is re-validated on the way in, so nothing enters the bundle that
has not had its checksums and provenance checked.

    python scripts/build_uw_bundle.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel.ingest import uw_bundle  # noqa: E402


def main() -> int:
    started = time.time()
    print("validating every country export and stacking it")
    bundle = uw_bundle.build()

    print(
        f"  {len(bundle.iso3)} locations x {bundle.n_draws:,} trajectories x "
        f"{len(bundle.years)} years"
    )
    print(f"  years {int(bundle.years[0])}-{int(bundle.years[-1])}")

    forecast = bundle.forecast_mask()
    tfr = bundle.tfr[forecast]
    e0f = bundle.e0_female[forecast]
    print(
        f"  TFR   {tfr.min():.3f} to {tfr.max():.3f}   "
        f"female e0 {e0f.min():.1f} to {e0f.max():.1f}"
    )

    path = uw_bundle.save(bundle)
    size = path.stat().st_size / 1024**2
    print(f"\nwrote {path} ({size:.0f} MB) in {time.time() - started:.0f}s")
    print(f"wrote {path.with_suffix('.json')}")

    # Read it straight back. A bundle that cannot be reloaded is not a bundle.
    reloaded = uw_bundle.load(path)
    if not np.array_equal(reloaded.tfr, bundle.tfr):
        raise SystemExit("the reloaded bundle does not match what was written")
    first = next(iter(reloaded))
    print(
        f"reload ok: first draw {first.draw_id}, {len(first.locations)} locations, "
        f"{int(first.years[0])}-{int(first.years[-1])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the projection input bundle from the downloaded WPP files.

    python scripts/build_bundle.py

Takes a few minutes: it reads about a gigabyte of gzipped CSV. Writes
data/processed/wpp2024_bundle.npz plus a .json recording the source checksums.
Both are regenerable, so neither is committed; the checksums that make them
reproducible are.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    t0 = time.time()
    print("Building projection bundle from WPP 2024\n")
    bundle = wpp.build_bundle()
    path = wpp.save_bundle(bundle)
    size = path.stat().st_size / 1e6
    print(f"\nWrote {path.relative_to(paths.REPO_ROOT)} ({size:.1f} MB) in {time.time() - t0:.0f}s")
    print(f"      {path.with_suffix('.json').relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

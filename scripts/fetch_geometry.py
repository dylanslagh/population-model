"""Download the country outlines for the map.

    python scripts/fetch_geometry.py

About 6 MB, pinned to a tagged Natural Earth release so the shapes cannot move
under a stored result.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.sources import fetch, naturalearth  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    print(f"Natural Earth {naturalearth.RELEASE}, {naturalearth.SCALE} scale")
    print(f"{naturalearth.SOURCE}\n")
    total = 0
    for key in naturalearth.LAYERS:
        r = fetch.fetch_geometry(key)
        total += r.bytes
    print(f"\n{len(naturalearth.LAYERS)} layers, {total / 1e6:.1f} MB.")
    print(f"Checksums in {fetch.manifest_path(fetch.GEO_MANIFEST).relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

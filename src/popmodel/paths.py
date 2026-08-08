"""Where everything lives.

One module so that no other file ever hard-codes a directory. If the repo moves
or the data directory is relocated, this is the only thing that changes.
"""

from __future__ import annotations

import os
from pathlib import Path

# src/popmodel/paths.py -> src/popmodel -> src -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# Allow an override so a big data directory can live off OneDrive if it ever
# needs to. Unset by default; the repo is self-contained without it.
_env_data = os.environ.get("POPMODEL_DATA_DIR")
DATA = Path(_env_data).resolve() if _env_data else REPO_ROOT / "data"

RAW = DATA / "raw"  # exactly as downloaded, never edited (gitignored)
INTERIM = DATA / "interim"  # scratch during ingest (gitignored)
PROCESSED = DATA / "processed"  # compact arrays the model reads (gitignored)
MANIFEST = DATA / "manifest"  # checksums + provenance (committed)
REFERENCE = DATA / "reference"  # hand-maintained tables, e.g. crosswalk (committed)

OUT = REPO_ROOT / "out"  # figures, reports (gitignored)
VINTAGES = REPO_ROOT / "vintages"  # immutable stored predictions (committed)


def ensure_dirs() -> None:
    """Create the directories that are not committed to git."""
    for d in (RAW, INTERIM, PROCESSED, MANIFEST, REFERENCE, OUT, VINTAGES):
        d.mkdir(parents=True, exist_ok=True)

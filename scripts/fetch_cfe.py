"""Download the pinned CFE aggregate cohort-parity tables.

Raw files stay gitignored under ``data/raw/CFE`` because the CFE terms ask
users not to redistribute copies.  The committed manifest records exactly
which bytes supported the derived parameter audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths
from popmodel.sources import cfe
from popmodel.sources.fetch import ChecksumMismatch, _download, sha256_of


MANIFEST = paths.MANIFEST / "cfe_files.json"
RAW = paths.RAW / "CFE"


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        "manifest": "cfe_files",
        "source": "Cohort Fertility and Education Database",
        "source_page": cfe.SOURCE_PAGE,
        "methods": cfe.METHODS,
        "terms": cfe.TERMS,
        "accessed": cfe.ACCESSED,
        "redistribution": (
            "Raw aggregate tabulations are research-only and must not be "
            "redistributed. They remain gitignored; this manifest and derived "
            "summaries contain no original cell counts."
        ),
        "files": {},
    }


def save_manifest(manifest: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def fetch(key: str, *, force: bool = False) -> Path:
    dataset = cfe.DATASETS[key]
    dest = RAW / dataset.filename
    manifest = load_manifest()
    recorded = manifest["files"].get(key)

    if force or not dest.exists():
        print(f"  {dataset.country}: {dataset.source}")
        _download(dataset.url, dest)

    digest = sha256_of(dest)
    size = dest.stat().st_size
    if recorded and recorded["sha256"] != digest:
        raise ChecksumMismatch(
            f"{dataset.filename} no longer matches the committed CFE manifest.\n"
            f"  expected {recorded['sha256']} ({recorded['bytes']} bytes)\n"
            f"  found    {digest} ({size} bytes)\n"
            "The database may have corrected the source. Review the country "
            "documentation and resulting parameter before updating the hash."
        )
    if not recorded:
        manifest["files"][key] = {
            "country": dataset.country,
            "data_source": dataset.source,
            "observation_year": dataset.observation_year,
            "filename": dataset.filename,
            "url": dataset.url,
            "sha256": digest,
            "bytes": size,
            "first_downloaded": date.today().isoformat(),
        }
        save_manifest(manifest)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("keys", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.list:
        for key, d in cfe.DATASETS.items():
            print(f"{key:28s} {d.country:22s} {d.source}")
        return

    keys = args.keys or list(cfe.DATASETS)
    unknown = sorted(set(keys) - set(cfe.DATASETS))
    if unknown:
        raise SystemExit(f"unknown CFE dataset keys: {', '.join(unknown)}")
    for key in keys:
        fetch(key, force=args.force)
    print(f"verified {len(keys)} CFE datasets; manifest: {MANIFEST}")


if __name__ == "__main__":
    main()


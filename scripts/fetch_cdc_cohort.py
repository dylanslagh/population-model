"""Download and verify the two CDC/NCHS cohort-fertility source tables.

This public table is an independent U.S. check on the multi-country CFE
calculation.  The raw CSV stays gitignored; its URL and checksum are committed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths
from popmodel.sources import cdc_cohort
from popmodel.sources.fetch import ChecksumMismatch, _download, sha256_of


RAW = paths.RAW / "CDC"
MANIFEST = paths.MANIFEST / "cdc_cohort_files.json"
FILES = {
    "distribution": ("Table03.csv", cdc_cohort.DISTRIBUTION_URL),
    "cumulative_rates": ("Table02.csv", cdc_cohort.CUMULATIVE_RATES_URL),
}


def main() -> None:
    if MANIFEST.exists():
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
        recorded_files = recorded.get("files")
        if recorded_files is None:
            recorded_files = {"distribution": recorded.pop("file")}
    else:
        recorded = {
            "manifest": "cdc_cohort_files",
            "source": "CDC/NCHS Cohort Fertility Tables",
            "source_page": cdc_cohort.SOURCE_PAGE,
            "technical_appendix": cdc_cohort.TECHNICAL_APPENDIX,
            "accessed": cdc_cohort.ACCESSED,
        }
        recorded_files = {}

    for key, (filename, url) in FILES.items():
        path = RAW / filename
        if not path.exists():
            _download(url, path)
        digest = sha256_of(path)
        size = path.stat().st_size
        if key in recorded_files and recorded_files[key]["sha256"] != digest:
            raise ChecksumMismatch(
                f"CDC {filename} changed since the committed manifest; review "
                "the official revision and derived U.S. check before updating it"
            )
        recorded_files[key] = {
            "url": url,
            "filename": filename,
            "sha256": digest,
            "bytes": size,
        }

    recorded["files"] = recorded_files
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(recorded, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"verified {len(FILES)} CDC cohort tables; manifest: {MANIFEST}")


if __name__ == "__main__":
    main()

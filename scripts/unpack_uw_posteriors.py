"""Verify and safely unpack the downloaded UW trajectory archives.

This never overwrites an existing extraction.  Every source archive is
re-hashed against the manifest before any member is written.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel.sources import uw_extract, uw_wpp2024  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="archive keys (default: both)")
    parser.add_argument(
        "--verify-only", action="store_true", help="verify archives without unpacking"
    )
    parser.add_argument(
        "--min-free-gb", type=float, default=25.0,
        help="minimum free space required before extraction (default: 25)",
    )
    args = parser.parse_args()
    keys = args.keys or uw_wpp2024.REQUIRED_KEYS
    unknown = [key for key in keys if key not in uw_wpp2024.ARCHIVES]
    if unknown:
        parser.error(f"unknown archive key(s): {', '.join(unknown)}")
    if args.min_free_gb < 0:
        parser.error("--min-free-gb cannot be negative")

    if args.verify_only:
        for key in keys:
            result = uw_extract.verify_uw_archive(key)
            print(f"  ok  {key}: {result.bytes / 1e9:.2f} GB, SHA-256 verified")
        return 0

    results = uw_extract.unpack_uw_all(
        keys, min_free_bytes=int(args.min_free_gb * 1024**3)
    )
    for result in results:
        print(
            f"  ok  {result.key}: {result.files:,} files, "
            f"{result.expanded_bytes / 1e9:.2f} GB expanded\n"
            f"      {result.simulation_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Download the pinned UW WPP2024-aligned Bayesian trajectory archives.

    python scripts/fetch_uw_posteriors.py --list
    python scripts/fetch_uw_posteriors.py
    python scripts/fetch_uw_posteriors.py tfr_annual
    python scripts/fetch_uw_posteriors.py --check

The annual TFR and e0 archives total about 2.24 GB compressed. They are
University of Washington products, not official UN products. UW publishes no
cryptographic checksums for them, so this project verifies the publisher's byte
length and pins a SHA-256 hash on the first successful download.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.sources import fetch, uw_wpp2024  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("keys", nargs="*", help="archive keys (default: both annual products)")
    ap.add_argument("--list", action="store_true", help="list archives and exit")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--check", action="store_true", help="verify downloaded archives")
    args = ap.parse_args()

    if args.list:
        print(f"{uw_wpp2024.REVISION_LABEL}\n{uw_wpp2024.SOURCE_PAGE}\n")
        for key, archive in uw_wpp2024.ARCHIVES.items():
            path = paths.RAW / uw_wpp2024.REVISION / archive.filename
            flag = "present" if path.exists() else "missing"
            print(
                f"  {key:14s} {archive.expected_bytes / 1e9:4.2f} GB  {flag}\n"
                f"      {archive.purpose}\n"
                f"      read with {archive.package} {archive.package_version}\n"
            )
        print(
            f"Expected: {uw_wpp2024.EXPECTED_TRAJECTORIES:,} trajectories for "
            f"{uw_wpp2024.EXPECTED_LOCATIONS} locations, with a "
            f"{uw_wpp2024.TRAJECTORY_ANCHOR_YEAR} anchor and forecasts from "
            f"{uw_wpp2024.FORECAST_START}-{uw_wpp2024.FORECAST_END}.\n"
            f"{uw_wpp2024.LOCATION_RECONCILIATION}"
        )
        return 0

    keys = args.keys or uw_wpp2024.REQUIRED_KEYS
    unknown = [key for key in keys if key not in uw_wpp2024.ARCHIVES]
    if unknown:
        print(f"Unknown archive key(s): {', '.join(unknown)}\nTry --list.", file=sys.stderr)
        return 2

    paths.ensure_dirs()
    if args.check:
        manifest = fetch.load_uw_manifest()
        if not manifest["files"]:
            print("UW manifest is empty - nothing has been downloaded yet.")
            return 1
        problems = 0
        for key in keys:
            record = manifest["files"].get(key)
            if record is None:
                print(f"  NOT RECORDED  {key}")
                problems += 1
                continue
            archive = uw_wpp2024.ARCHIVES[key]
            path = paths.RAW / uw_wpp2024.REVISION / record["filename"]
            if not path.exists():
                print(f"  MISSING   {key}")
                problems += 1
                continue
            size_ok = path.stat().st_size == archive.expected_bytes
            hash_ok = size_ok and fetch.sha256_of(path) == record["sha256"]
            print(f"  {'ok      ' if hash_ok else 'MISMATCH'}  {key}")
            problems += 0 if hash_ok else 1
        print("\nall archives verified" if not problems else f"\n{problems} problem(s)")
        return 0 if not problems else 1

    total = sum(uw_wpp2024.ARCHIVES[key].expected_bytes for key in keys)
    print(
        f"Fetching {len(keys)} UW archive(s), {total / 1e9:.2f} GB compressed.\n"
        "These are UW products aligned to WPP 2024, not official UN products.\n"
    )
    results = fetch.fetch_uw_all(keys, force=args.force)
    fresh = sum(result.downloaded for result in results)
    print(f"\n{len(results)} archive(s) verified; {fresh} newly downloaded.")
    print(f"Manifest: {fetch.manifest_path(fetch.UW_MANIFEST).relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

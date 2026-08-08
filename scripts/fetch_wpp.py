"""Download the pinned WPP 2024 files.

    python scripts/fetch_wpp.py              # everything the model needs
    python scripts/fetch_wpp.py --list       # what there is, and why
    python scripts/fetch_wpp.py fertility_age1 indicators_medium
    python scripts/fetch_wpp.py --check      # re-verify checksums, no download

About a gigabyte, compressed, on a full run. It only has to happen once; the
files are gitignored and the checksums are committed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.sources import fetch, wpp2024  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*", help="file keys to fetch (default: all required)")
    ap.add_argument("--list", action="store_true", help="list available files and exit")
    ap.add_argument("--all", action="store_true", help="include optional files")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--check", action="store_true", help="verify checksums of what is already here")
    args = ap.parse_args()

    if args.list:
        print(f"{wpp2024.REVISION_LABEL}\n{wpp2024.SOURCE_PAGE}\n")
        for key, f in wpp2024.FILES.items():
            here = (paths.RAW / wpp2024.REVISION / f.filename).exists()
            flag = "present" if here else "missing"
            tag = "" if f.required else "  [optional]"
            print(f"  {key:24s} ~{f.approx_mb:4d} MB  {flag:7s}{tag}\n      {f.purpose}\n")
        return 0

    paths.ensure_dirs()

    if args.check:
        manifest = fetch.load_manifest()
        if not manifest["files"]:
            print("Manifest is empty — nothing has been downloaded yet.")
            return 1
        bad = 0
        for key, rec in sorted(manifest["files"].items()):
            p = paths.RAW / wpp2024.REVISION / rec["filename"]
            if not p.exists():
                print(f"  MISSING   {key}")
                bad += 1
                continue
            digest = fetch.sha256_of(p)
            ok = digest == rec["sha256"]
            print(f"  {'ok      ' if ok else 'MISMATCH'}  {key}")
            bad += 0 if ok else 1
        print("\nall files verified" if not bad else f"\n{bad} problem(s)")
        return 0 if not bad else 1

    keys = args.keys or (list(wpp2024.FILES) if args.all else wpp2024.REQUIRED_KEYS)
    unknown = [k for k in keys if k not in wpp2024.FILES]
    if unknown:
        print(f"Unknown file key(s): {', '.join(unknown)}\nTry --list.", file=sys.stderr)
        return 2

    print(f"Fetching {len(keys)} file(s) from {wpp2024.REVISION_LABEL}\n")
    results = fetch.fetch_all(keys, force=args.force)
    total = sum(r.bytes for r in results)
    fresh = sum(1 for r in results if r.downloaded)
    print(f"\n{len(results)} file(s), {total / 1e9:.2f} GB on disk, {fresh} newly downloaded.")
    print(f"Checksums recorded in {fetch.manifest_path().relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

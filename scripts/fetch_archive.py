"""Download archived WPP revisions.

    python scripts/fetch_archive.py            # 1992-2008, about 590 MB
    python scripts/fetch_archive.py --list
    python scripts/fetch_archive.py wpp2010    # a later one, on request

These are historical records, not model inputs. A revision published in 1994
will never legitimately change, so the checksum check on re-download is
stricter in intent than the one for current data: a mismatch means something is
wrong, not that the UN updated something.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402
from popmodel.sources import fetch, wpp_archive  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*", help="revision keys, e.g. wpp1994 (default: 1992-2008)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true", help="every revision, including the 6.6 GB one")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.list:
        print(f"Archived WPP revisions\n{wpp_archive.SOURCE_PAGE} -> file type 'Archive'\n")
        print(f"  {'key':<10} {'size':>8}  {'base':>5}  {'hindsight':>9}  status")
        for key, rev in wpp_archive.REVISIONS.items():
            here = (paths.RAW / "archive" / rev.filename).exists()
            years = 2024 - rev.base_year
            tag = "" if rev.in_default_set else "   (not in default set)"
            print(f"  {key:<10} {rev.approx_mb:>6} MB  {rev.base_year:>5}  "
                  f"{years:>7}yr  {'present' if here else 'missing'}{tag}")
        return 0

    paths.ensure_dirs()
    keys = args.keys or (list(wpp_archive.REVISIONS) if args.all else wpp_archive.DEFAULT_KEYS)
    unknown = [k for k in keys if k not in wpp_archive.REVISIONS]
    if unknown:
        print(f"Unknown revision(s): {', '.join(unknown)}. Try --list.", file=sys.stderr)
        return 2

    print(f"Fetching {len(keys)} archived revision(s)\n")
    total = 0
    for key in keys:
        r = fetch.fetch_archive(key, force=args.force)
        total += r.bytes
    print(f"\n{len(keys)} revision(s), {total / 1e9:.2f} GB on disk.")
    print(f"Checksums in {fetch.manifest_path(fetch.ARCHIVE_MANIFEST).relative_to(paths.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Download source files and record exactly what was downloaded.

Two jobs:

1. Get the file (resumable, because these run to hundreds of megabytes).
2. Write down its SHA-256, size, URL and the date it arrived, in a manifest
   that IS committed to git.

The manifest is trust-on-first-use: the first successful download of a file
defines the checksum, and every run after that verifies against it. If the UN
silently re-issues a file under the same name, this fails loudly instead of
letting the change leak into results months later. Spec section 14 rule 5 is
about country codes, but the same instinct applies to the bytes themselves.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from popmodel import paths
from popmodel.sources import wpp2024

_CHUNK = 1 << 20  # 1 MiB
_USER_AGENT = "population-model/0.0.1 (research; contact via github.com/dylanslagh)"


class ChecksumMismatch(RuntimeError):
    """A file on disk does not match the checksum recorded in the manifest."""


@dataclass
class FetchResult:
    key: str
    path: Path
    sha256: str
    bytes: int
    downloaded: bool  # False means it was already present and verified


def manifest_path(revision: str = wpp2024.REVISION) -> Path:
    return paths.MANIFEST / f"{revision.lower()}_files.json"


def load_manifest(revision: str = wpp2024.REVISION) -> dict:
    p = manifest_path(revision)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "revision": revision,
        "revision_label": wpp2024.REVISION_LABEL,
        "source_page": wpp2024.SOURCE_PAGE,
        "files": {},
    }


def save_manifest(manifest: dict, revision: str = wpp2024.REVISION) -> None:
    paths.MANIFEST.mkdir(parents=True, exist_ok=True)
    manifest_path(revision).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path, *, retries: int = 4) -> None:
    """Stream a URL to disk, resuming a partial file if one is there."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                # A server that ignores Range replies 200 and sends the lot;
                # in that case start over rather than concatenating garbage.
                resuming = resp.status == 206
                mode = "ab" if (have and resuming) else "wb"
                total = resp.headers.get("Content-Length")
                total = (int(total) + (have if resuming else 0)) if total else None
                written = have if resuming else 0
                next_report = 0.0
                with part.open(mode) as fh:
                    while True:
                        block = resp.read(_CHUNK)
                        if not block:
                            break
                        fh.write(block)
                        written += len(block)
                        # Report every 10%, not every megabyte: this runs
                        # unattended and the log gets read later.
                        pct = 100.0 * written / total if total else 0.0
                        if total and pct >= next_report:
                            print(f"    {written / 1e6:8.1f} MB / {total / 1e6:.1f} MB  ({pct:5.1f}%)")
                            next_report += 10.0
                print(f"    done: {written / 1e6:.1f} MB")
            part.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt == retries:
                raise
            wait = 2**attempt
            print(f"\n    {type(exc).__name__}: {exc}; retrying in {wait}s")
            time.sleep(wait)


def fetch_one(key: str, *, force: bool = False, verify: bool = True) -> FetchResult:
    spec = wpp2024.FILES[key]
    dest = paths.RAW / wpp2024.REVISION / spec.filename
    manifest = load_manifest()
    recorded = manifest["files"].get(key)

    downloaded = False
    if force or not dest.exists():
        print(f"  {spec.filename}  (~{spec.approx_mb} MB)")
        _download(spec.url, dest)
        downloaded = True

    size = dest.stat().st_size
    digest = sha256_of(dest) if (verify or downloaded or not recorded) else recorded["sha256"]

    if recorded and recorded["sha256"] != digest:
        raise ChecksumMismatch(
            f"{spec.filename} does not match the manifest.\n"
            f"  expected {recorded['sha256']} ({recorded['bytes']} bytes, "
            f"first seen {recorded['first_downloaded']})\n"
            f"  found    {digest} ({size} bytes)\n"
            "Either the local file is damaged (delete it and re-fetch) or the UN "
            "re-issued the file under the same name. Do not proceed until you "
            "know which: every stored result is tied to these bytes."
        )

    if not recorded:
        manifest["files"][key] = {
            "filename": spec.filename,
            "url": spec.url,
            "purpose": spec.purpose,
            "sha256": digest,
            "bytes": size,
            "first_downloaded": date.today().isoformat(),
        }
        save_manifest(manifest)

    return FetchResult(key=key, path=dest, sha256=digest, bytes=size, downloaded=downloaded)


def fetch_all(
    keys: list[str] | None = None, *, force: bool = False, verify: bool = True
) -> list[FetchResult]:
    keys = keys or wpp2024.REQUIRED_KEYS
    results = []
    for key in keys:
        results.append(fetch_one(key, force=force, verify=verify))
    return results


def raw_path(key: str) -> Path:
    """Path to a fetched file. Raises if it is not there yet."""
    spec = wpp2024.FILES[key]
    p = paths.RAW / wpp2024.REVISION / spec.filename
    if not p.exists():
        raise FileNotFoundError(
            f"{spec.filename} has not been downloaded.\n"
            f"  Run:  python scripts/fetch_wpp.py {key}"
        )
    return p

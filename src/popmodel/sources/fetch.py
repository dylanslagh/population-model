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
from popmodel.sources import naturalearth, unsd_census, uw_wpp2024, wpp2024, wpp_archive

_CHUNK = 1 << 20  # 1 MiB
_USER_AGENT = "population-model/0.0.1 (research; contact via github.com/dylanslagh)"


class ChecksumMismatch(RuntimeError):
    """A file on disk does not match the checksum recorded in the manifest."""


class SourceSizeMismatch(RuntimeError):
    """A source archive no longer has the byte length verified from its publisher."""


@dataclass
class FetchResult:
    key: str
    path: Path
    sha256: str
    bytes: int
    downloaded: bool  # False means it was already present and verified


_MAIN_MANIFEST = wpp2024.REVISION.lower()


def manifest_path(name: str = _MAIN_MANIFEST) -> Path:
    suffix = "" if name.endswith("_files") else "_files"
    return paths.MANIFEST / f"{name.lower()}{suffix}.json"


def load_manifest(name: str = _MAIN_MANIFEST) -> dict:
    p = manifest_path(name)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "manifest": name,
        "revision_label": wpp2024.REVISION_LABEL,
        "source_page": wpp2024.SOURCE_PAGE,
        "files": {},
    }


def save_manifest(manifest: dict, name: str = _MAIN_MANIFEST) -> None:
    paths.MANIFEST.mkdir(parents=True, exist_ok=True)
    manifest_path(name).write_text(
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


# ---------------------------------------------------------------------------
# UW posterior trajectories aligned to WPP 2024. These are UW products, not
# part of the UN input manifest above.
# ---------------------------------------------------------------------------

UW_MANIFEST = "uw_wpp2024_files"


def load_uw_manifest() -> dict:
    p = manifest_path(UW_MANIFEST)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "manifest": UW_MANIFEST,
        "revision": uw_wpp2024.REVISION,
        "revision_label": uw_wpp2024.REVISION_LABEL,
        "source_page": uw_wpp2024.SOURCE_PAGE,
        "vignette": uw_wpp2024.VIGNETTE,
        "urls_verified_on": uw_wpp2024.URLS_VERIFIED_ON,
        "publisher_note": "University of Washington product; not an official UN product",
        "checksum_policy": (
            "UW publishes no cryptographic checksums for these archives. The first "
            "successful download is hashed with SHA-256 and becomes authoritative "
            "for this project; the publisher-reported byte length is checked first."
        ),
        "files": {},
    }


def save_uw_manifest(manifest: dict) -> None:
    paths.MANIFEST.mkdir(parents=True, exist_ok=True)
    manifest_path(UW_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def uw_archive_path(key: str) -> Path:
    archive = uw_wpp2024.ARCHIVES[key]
    p = paths.RAW / uw_wpp2024.REVISION / archive.filename
    if not p.exists():
        raise FileNotFoundError(
            f"{archive.filename} has not been downloaded.\n"
            f"  Run:  python scripts/fetch_uw_posteriors.py {key}"
        )
    return p


def fetch_uw_archive(key: str, *, force: bool = False) -> FetchResult:
    archive = uw_wpp2024.ARCHIVES[key]
    dest = paths.RAW / uw_wpp2024.REVISION / archive.filename
    manifest = load_uw_manifest()
    recorded = manifest["files"].get(key)

    downloaded = False
    if force or not dest.exists():
        print(f"  {archive.filename}  ({archive.expected_bytes / 1e9:.2f} GB)")
        _download(archive.url, dest)
        downloaded = True

    size = dest.stat().st_size
    if size != archive.expected_bytes:
        raise SourceSizeMismatch(
            f"{archive.filename} has {size:,} bytes; the official URL returned "
            f"{archive.expected_bytes:,} bytes when verified on "
            f"{uw_wpp2024.URLS_VERIFIED_ON}. Do not treat the ETag as a checksum. "
            "Re-check the UW download page and creation script before updating "
            "the expected size."
        )
    digest = sha256_of(dest)
    if recorded and recorded["sha256"] != digest:
        raise ChecksumMismatch(
            f"{archive.filename} does not match the project's first-download hash.\n"
            f"  expected {recorded['sha256']} ({recorded['bytes']} bytes)\n"
            f"  found    {digest} ({size} bytes)\n"
            "The local archive is damaged or UW replaced it in place. Investigate "
            "before exporting any trajectories."
        )

    if not recorded:
        manifest["files"][key] = {
            "filename": archive.filename,
            "url": archive.url,
            "purpose": archive.purpose,
            "package": archive.package,
            "package_version": archive.package_version,
            "unpacked_sim_dir": archive.unpacked_sim_dir,
            "creation_script_url": archive.creation_script_url,
            "sha256": digest,
            "bytes": size,
            "first_downloaded": date.today().isoformat(),
            "url_verified_on": uw_wpp2024.URLS_VERIFIED_ON,
            "etag_when_verified": archive.etag_when_verified,
            "last_modified_when_verified": archive.last_modified_when_verified,
        }
        save_uw_manifest(manifest)

    return FetchResult(key, dest, digest, size, downloaded)


def fetch_uw_all(
    keys: list[str] | None = None, *, force: bool = False
) -> list[FetchResult]:
    return [
        fetch_uw_archive(key, force=force)
        for key in (keys or uw_wpp2024.REQUIRED_KEYS)
    ]


# ---------------------------------------------------------------------------
# The archived revisions. Same download and checksum discipline, separate
# manifest, because they are a different kind of thing: not inputs to the
# model but the record it is graded against.
# ---------------------------------------------------------------------------

ARCHIVE_MANIFEST = "wpp_archive_files"


def archive_path(key: str) -> Path:
    rev = wpp_archive.REVISIONS[key]
    p = paths.RAW / "archive" / rev.filename
    if not p.exists():
        raise FileNotFoundError(
            f"{rev.filename} has not been downloaded.\n"
            f"  Run:  python scripts/fetch_archive.py {key}"
        )
    return p


GEO_MANIFEST = "naturalearth_files"


def geo_path(key: str) -> Path:
    layer = naturalearth.LAYERS[key]
    p = paths.RAW / "naturalearth" / naturalearth.RELEASE / layer.filename
    if not p.exists():
        raise FileNotFoundError(
            f"{layer.filename} has not been downloaded.\n"
            f"  Run:  python scripts/fetch_geometry.py"
        )
    return p


def fetch_geometry(key: str, *, force: bool = False) -> FetchResult:
    layer = naturalearth.LAYERS[key]
    dest = paths.RAW / "naturalearth" / naturalearth.RELEASE / layer.filename
    manifest = load_manifest(GEO_MANIFEST)
    recorded = manifest["files"].get(key)

    downloaded = False
    if force or not dest.exists():
        print(f"  {layer.filename}  (~{layer.approx_mb} MB)")
        _download(layer.url, dest)
        downloaded = True

    digest = sha256_of(dest)
    if recorded and recorded["sha256"] != digest:
        raise ChecksumMismatch(
            f"{layer.filename} does not match the manifest.\n"
            f"  expected {recorded['sha256']}\n  found    {digest}\n"
            f"This is pinned to Natural Earth {naturalearth.RELEASE}, a tagged "
            "release, so the bytes should never move. Investigate."
        )
    if not recorded:
        manifest["files"][key] = {
            "filename": layer.filename,
            "url": layer.url,
            "release": naturalearth.RELEASE,
            "sha256": digest,
            "bytes": dest.stat().st_size,
            "first_downloaded": date.today().isoformat(),
        }
        save_manifest(manifest, GEO_MANIFEST)

    return FetchResult(key=key, path=dest, sha256=digest, bytes=dest.stat().st_size,
                       downloaded=downloaded)


def fetch_archive(key: str, *, force: bool = False) -> FetchResult:
    rev = wpp_archive.REVISIONS[key]
    dest = paths.RAW / "archive" / rev.filename
    manifest = load_manifest(ARCHIVE_MANIFEST)
    recorded = manifest["files"].get(key)

    downloaded = False
    if force or not dest.exists():
        print(f"  {rev.filename}  (~{rev.approx_mb} MB)")
        _download(rev.url, dest)
        downloaded = True

    digest = sha256_of(dest)
    if recorded and recorded["sha256"] != digest:
        raise ChecksumMismatch(
            f"{rev.filename} does not match the manifest.\n"
            f"  expected {recorded['sha256']}\n  found    {digest}\n"
            "An archived revision is a historical record and should never "
            "change. Investigate before proceeding."
        )
    if not recorded:
        manifest["files"][key] = {
            "filename": rev.filename,
            "url": rev.url,
            "revision_year": rev.year,
            "sha256": digest,
            "bytes": dest.stat().st_size,
            "first_downloaded": date.today().isoformat(),
        }
        save_manifest(manifest, ARCHIVE_MANIFEST)

    return FetchResult(key=key, path=dest, sha256=digest, bytes=dest.stat().st_size,
                       downloaded=downloaded)


CENSUS_MANIFEST = "unsd_files"


def census_page(*, force: bool = False) -> Path:
    """The UNSD census-dates page, downloaded and checksummed like everything else.

    It is a live HTML page rather than a dated release, so the checksum will
    legitimately change when UNSD updates it. A mismatch is therefore news, not
    an error: it means a country has counted its people since last time.
    """
    dest = paths.RAW / "unsd" / "census_dates.html"
    manifest = load_manifest(CENSUS_MANIFEST)
    recorded = manifest["files"].get("census_dates")

    if force or not dest.exists():
        print("  UNSD census dates page")
        _download(unsd_census.URL, dest)

    digest = sha256_of(dest)
    if recorded and recorded["sha256"] != digest:
        print(f"  note: the UNSD page has changed since {recorded['first_downloaded']}. "
              "That is expected over time - censuses happen.")
    if not recorded or recorded["sha256"] != digest:
        manifest["files"]["census_dates"] = {
            "filename": dest.name,
            "url": unsd_census.URL,
            "source": unsd_census.SOURCE,
            "sha256": digest,
            "bytes": dest.stat().st_size,
            "first_downloaded": (recorded or {}).get("first_downloaded",
                                                     date.today().isoformat()),
            "last_changed": date.today().isoformat(),
        }
        save_manifest(manifest, CENSUS_MANIFEST)
    return dest

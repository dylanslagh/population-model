"""Verify and safely unpack the native UW trajectory archives.

The archives are large, directory-backed R objects.  They are never read from
an unverified download and never unpacked directly over an existing directory.
Each archive gets its own atomic extraction directory and a marker tied to the
SHA-256 in the committed source manifest.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from popmodel import paths
from popmodel.sources import fetch, uw_wpp2024

DEFAULT_MIN_FREE_BYTES = 25 * 1024**3


class UwExtractionError(RuntimeError):
    """The archive cannot be trusted or safely extracted."""


class UnsafeArchiveMember(UwExtractionError):
    """A tar member could escape the destination or create a special file."""


@dataclass(frozen=True)
class VerifiedUwArchive:
    key: str
    path: Path
    sha256: str
    bytes: int


@dataclass(frozen=True)
class UnpackedUwArchive:
    key: str
    archive_sha256: str
    root: Path
    simulation_dir: Path
    files: int
    expanded_bytes: int


def verify_uw_archive(key: str) -> VerifiedUwArchive:
    """Re-hash one archive and match it to both the source spec and manifest."""
    if key not in uw_wpp2024.ARCHIVES:
        raise KeyError(f"unknown UW archive key {key!r}")
    spec = uw_wpp2024.ARCHIVES[key]
    manifest = fetch.load_uw_manifest()
    record = manifest.get("files", {}).get(key)
    if record is None:
        raise UwExtractionError(
            f"{key} is not recorded in the UW manifest; finish and verify the "
            "download before unpacking it"
        )
    if record.get("filename") != spec.filename:
        raise UwExtractionError(
            f"{key} manifest names {record.get('filename')!r}, expected "
            f"{spec.filename!r}"
        )

    archive = fetch.uw_archive_path(key)
    size = archive.stat().st_size
    if size != spec.expected_bytes or record.get("bytes") != size:
        raise UwExtractionError(
            f"{spec.filename} has {size:,} bytes, but its source definition and "
            "manifest do not both agree with that size"
        )
    digest = fetch.sha256_of(archive)
    if record.get("sha256") != digest:
        raise fetch.ChecksumMismatch(
            f"{spec.filename} does not match the UW manifest before extraction\n"
            f"  expected {record.get('sha256')}\n"
            f"  found    {digest}"
        )
    return VerifiedUwArchive(key, archive, digest, size)


def _validated_members(
    archive: tarfile.TarFile, destination: Path
) -> tuple[list[tarfile.TarInfo], int, int]:
    """Validate every member before extracting the first one."""
    root = destination.resolve()
    members = archive.getmembers()
    expanded_bytes = 0
    files = 0
    seen: set[str] = set()
    windows_devices = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
    for member in members:
        name = member.name
        if not name or "\x00" in name:
            raise UnsafeArchiveMember("UW archive contains an empty or invalid path")
        member_path = Path(name.replace("/", os.sep))
        if member_path.is_absolute() or member_path.drive:
            raise UnsafeArchiveMember(f"absolute archive path refused: {name!r}")
        for part in member_path.parts:
            device = part.rstrip(" .").split(".", 1)[0].upper()
            if ":" in part or device in windows_devices:
                raise UnsafeArchiveMember(f"unsafe Windows archive path: {name!r}")
        identity = str(member_path).rstrip(" .").casefold()
        if identity in seen:
            raise UnsafeArchiveMember(f"duplicate archive path refused: {name!r}")
        seen.add(identity)
        candidate = (destination / member_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise UnsafeArchiveMember(
                f"archive path would leave the extraction directory: {name!r}"
            ) from exc
        if not (member.isdir() or member.isfile()):
            raise UnsafeArchiveMember(
                f"archive links and special files are not allowed: {name!r}"
            )
        if member.isfile():
            files += 1
            expanded_bytes += int(member.size)
    return members, files, expanded_bytes


def _marker_matches(marker: Path, *, key: str, sha256: str) -> bool:
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return value.get("archive_key") == key and value.get("archive_sha256") == sha256


def unpack_uw_archive(
    key: str,
    *,
    destination: Path | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
) -> UnpackedUwArchive:
    """Safely extract one verified archive into an archive-specific directory.

    Existing unmarked or differently marked directories are refused rather
    than overwritten.  Removing an obsolete extraction is therefore a visible
    human decision, not a side effect of this function.
    """
    if min_free_bytes < 0:
        raise ValueError("min_free_bytes cannot be negative")
    verified = verify_uw_archive(key)
    spec = uw_wpp2024.ARCHIVES[key]
    native_root = Path(destination) if destination is not None else (
        paths.INTERIM / uw_wpp2024.REVISION / "native"
    )
    target = native_root / key
    expected = target / Path(spec.unpacked_sim_dir)
    marker = target / ".verified-extraction.json"

    if target.exists():
        if expected.is_dir() and _marker_matches(
            marker, key=key, sha256=verified.sha256
        ):
            value = json.loads(marker.read_text(encoding="utf-8"))
            return UnpackedUwArchive(
                key=key,
                archive_sha256=verified.sha256,
                root=target,
                simulation_dir=expected,
                files=int(value["files"]),
                expanded_bytes=int(value["expanded_bytes"]),
            )
        raise UwExtractionError(
            f"refusing to overwrite unverified or stale extraction directory {target}"
        )

    native_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(native_root).free
    if free < min_free_bytes:
        raise UwExtractionError(
            f"only {free / 1024**3:.1f} GB is free at {native_root}; "
            f"at least {min_free_bytes / 1024**3:.1f} GB is required before "
            "unpacking the UW archives"
        )

    staging = native_root / f".staging-{key}-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        with tarfile.open(verified.path, mode="r:gz") as archive:
            members, files, expanded_bytes = _validated_members(archive, staging)
            if expanded_bytes > free:
                raise UwExtractionError(
                    f"{key} expands to {expanded_bytes / 1024**3:.1f} GB, more "
                    "than the available disk space"
                )
            for member in members:
                archive.extract(member, path=staging, set_attrs=True)

        staged_simulation = staging / Path(spec.unpacked_sim_dir)
        if not staged_simulation.is_dir():
            raise UwExtractionError(
                f"{key} did not contain its documented simulation directory "
                f"{spec.unpacked_sim_dir!r}"
            )
        marker_value = {
            "archive_key": key,
            "archive_filename": verified.path.name,
            "archive_sha256": verified.sha256,
            "archive_bytes": verified.bytes,
            "files": files,
            "expanded_bytes": expanded_bytes,
            "simulation_dir": spec.unpacked_sim_dir,
        }
        (staging / ".verified-extraction.json").write_text(
            json.dumps(marker_value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.replace(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return UnpackedUwArchive(
        key=key,
        archive_sha256=verified.sha256,
        root=target,
        simulation_dir=expected,
        files=files,
        expanded_bytes=expanded_bytes,
    )


def unpack_uw_all(
    keys: list[str] | None = None,
    *,
    destination: Path | None = None,
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES,
) -> list[UnpackedUwArchive]:
    """Verify and unpack the requested archives in their manifest order."""
    return [
        unpack_uw_archive(
            key, destination=destination, min_free_bytes=min_free_bytes
        )
        for key in (keys or uw_wpp2024.REQUIRED_KEYS)
    ]

"""UW archives are verified and path-safe before native R objects are exposed."""

from __future__ import annotations

import hashlib
import io
import tarfile
from dataclasses import replace

import pytest

from popmodel import paths
from popmodel.sources import fetch, uw_extract, uw_wpp2024


def _redirect_data(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "RAW", tmp_path / "raw")
    monkeypatch.setattr(paths, "MANIFEST", tmp_path / "manifest")
    monkeypatch.setattr(paths, "INTERIM", tmp_path / "interim")


def _record_archive(monkeypatch, tmp_path, members):
    _redirect_data(monkeypatch, tmp_path)
    key = "tfr_annual"
    original = uw_wpp2024.ARCHIVES[key]
    archive_path = paths.RAW / uw_wpp2024.REVISION / original.filename
    archive_path.parent.mkdir(parents=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, content in members:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    patched = replace(
        original,
        expected_bytes=archive_path.stat().st_size,
        unpacked_sim_dir="TFR1unc/sim20241101",
    )
    monkeypatch.setitem(uw_wpp2024.ARCHIVES, key, patched)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest = fetch.load_uw_manifest()
    manifest["files"][key] = {
        "filename": original.filename,
        "bytes": archive_path.stat().st_size,
        "sha256": digest,
    }
    fetch.save_uw_manifest(manifest)
    return key, digest


def test_verified_archive_is_atomically_unpacked_and_reused(monkeypatch, tmp_path):
    key, digest = _record_archive(
        monkeypatch,
        tmp_path,
        [("TFR1unc/sim20241101/predictions/prediction.rda", b"fixture")],
    )
    destination = tmp_path / "native"
    result = uw_extract.unpack_uw_archive(
        key, destination=destination, min_free_bytes=0
    )
    assert result.archive_sha256 == digest
    assert result.files == 1
    assert result.expanded_bytes == len(b"fixture")
    assert (result.simulation_dir / "predictions" / "prediction.rda").read_bytes() == b"fixture"
    assert (result.root / ".verified-extraction.json").is_file()

    again = uw_extract.unpack_uw_archive(
        key, destination=destination, min_free_bytes=0
    )
    assert again == result
    assert not list(destination.glob(".staging-*"))


def test_archive_path_traversal_is_refused_before_any_member_is_written(
    monkeypatch, tmp_path
):
    key, _ = _record_archive(
        monkeypatch,
        tmp_path,
        [
            ("../outside.txt", b"escape"),
            ("TFR1unc/sim20241101/predictions/prediction.rda", b"fixture"),
        ],
    )
    destination = tmp_path / "native"
    with pytest.raises(uw_extract.UnsafeArchiveMember, match="leave the extraction"):
        uw_extract.unpack_uw_archive(key, destination=destination, min_free_bytes=0)
    assert not (tmp_path / "outside.txt").exists()
    assert not (destination / key).exists()
    assert not list(destination.glob(".staging-*"))


def test_unrecorded_archive_is_not_opened(monkeypatch, tmp_path):
    _redirect_data(monkeypatch, tmp_path)
    with pytest.raises(uw_extract.UwExtractionError, match="not recorded"):
        uw_extract.verify_uw_archive("tfr_annual")

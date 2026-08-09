"""The large UW sources are pinned and fail loudly without network access."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace

import pytest

from popmodel import paths
from popmodel.sources import fetch, uw_wpp2024
from scripts import fetch_uw_posteriors


def redirect_data(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "RAW", tmp_path / "raw")
    monkeypatch.setattr(paths, "MANIFEST", tmp_path / "manifest")


def test_annual_uw_archives_are_pinned_to_verified_official_urls():
    assert set(uw_wpp2024.ARCHIVES) == {"tfr_annual", "e0_annual"}
    assert uw_wpp2024.EXPECTED_TRAJECTORIES == 1000
    assert uw_wpp2024.EXPECTED_LOCATIONS == 236
    assert uw_wpp2024.TRAJECTORY_ANCHOR_YEAR == 2023
    assert "Holy See" in uw_wpp2024.LOCATION_RECONCILIATION
    assert sum(a.expected_bytes for a in uw_wpp2024.ARCHIVES.values()) == 2_243_702_499
    for archive in uw_wpp2024.ARCHIVES.values():
        assert archive.url.startswith("https://bayespop.csss.washington.edu/data/")
        assert archive.filename.endswith("WPP2024.tgz")
        assert archive.package_version


def test_uw_manifest_says_these_are_not_un_products(monkeypatch, tmp_path):
    redirect_data(monkeypatch, tmp_path)
    manifest = fetch.load_uw_manifest()
    assert manifest["files"] == {}
    assert "not an official UN product" in manifest["publisher_note"]
    assert "no cryptographic checksums" in manifest["checksum_policy"]


def test_wrong_publisher_byte_length_is_refused_before_manifesting(monkeypatch, tmp_path):
    redirect_data(monkeypatch, tmp_path)

    def tiny_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"changed")

    monkeypatch.setattr(fetch, "_download", tiny_download)
    with pytest.raises(fetch.SourceSizeMismatch, match="official URL returned"):
        fetch.fetch_uw_archive("tfr_annual")
    assert not fetch.manifest_path(fetch.UW_MANIFEST).exists()


def test_first_download_hash_becomes_the_local_authority(monkeypatch, tmp_path):
    redirect_data(monkeypatch, tmp_path)
    original = uw_wpp2024.ARCHIVES["tfr_annual"]
    monkeypatch.setitem(
        uw_wpp2024.ARCHIVES, "tfr_annual", replace(original, expected_bytes=3)
    )

    def three_bytes(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"abc")

    monkeypatch.setattr(fetch, "_download", three_bytes)
    result = fetch.fetch_uw_archive("tfr_annual")
    manifest = fetch.load_uw_manifest()
    assert result.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert manifest["files"]["tfr_annual"]["sha256"] == result.sha256
    assert manifest["files"]["tfr_annual"]["package_version"] == "7.4-4"


def test_check_fails_when_only_one_required_archive_was_recorded(
    monkeypatch, tmp_path, capsys
):
    redirect_data(monkeypatch, tmp_path)
    manifest = fetch.load_uw_manifest()
    manifest["files"]["tfr_annual"] = {
        "filename": uw_wpp2024.ARCHIVES["tfr_annual"].filename,
        "sha256": "not-needed-because-the-file-is-missing",
    }
    fetch.save_uw_manifest(manifest)
    monkeypatch.setattr(sys, "argv", ["fetch_uw_posteriors.py", "--check"])

    assert fetch_uw_posteriors.main() == 1
    output = capsys.readouterr().out
    assert "NOT RECORDED  e0_annual" in output
    assert "all archives verified" not in output


def test_real_finland_fixture_receipt_matches_the_archive_manifest():
    source = json.loads(
        (paths.MANIFEST / "uw_wpp2024_files.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (paths.MANIFEST / "uw_wpp2024_finland_fixture.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture["archive_sha256"] == {
        key: source["files"][key]["sha256"] for key in uw_wpp2024.REQUIRED_KEYS
    }
    assert fixture["result"] == {
        "source_years": "2023-2100",
        "model_years": "2024-2100",
        "trajectories": 1000,
        "locations": 236,
        "missing_wpp_loc_ids": [336],
        "alignment_shift_values_per_component": 78,
    }

"""The R/Python boundary preserves source evidence and emits strict draws."""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from popmodel.ingest import uw
from scripts import export_uw_fixture


def _write_source_export(directory):
    directory.mkdir()
    source_codes = list(range(1, 236)) + [246]
    with (directory / "locations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("loc_id", "name"))
        for code in source_codes:
            writer.writerow((code, "Finland" if code == 246 else f"Location {code}"))

    with (directory / "trajectories.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(uw.TRAJECTORY_COLUMNS)
        for trajectory_id in range(1, 1001):
            for year in range(2023, 2101):
                writer.writerow((
                    246,
                    "Finland",
                    "FIN",
                    year,
                    trajectory_id,
                    1.4 + trajectory_id / 100_000 + (year - 2023) / 100_000,
                    82.0 + trajectory_id / 100_000 + (year - 2023) / 1_000,
                    78.0 + trajectory_id / 100_000 + (year - 2023) / 1_000,
                ))

    with (directory / "shifts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("component", "shift_index", "value"))
        for component in ("tfr", "e0_female", "e0_male"):
            writer.writerow((component, 1, 0.1))
            writer.writerow((component, 2, 0.2))
    (directory / "session-info.txt").write_text(
        "R version 4.4.2; synthetic test session\n", encoding="utf-8"
    )
    with (directory / "r-metadata.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("key", "value"))
        for row in (
            ("R_version", "4.4.2"),
            ("bayesTFR_version", "7.4-4"),
            ("bayesLife_version", "5.3-0"),
            ("loc_id", "246"),
            ("iso3", "FIN"),
            ("country", "Finland"),
            ("year_start", "2023"),
            ("year_end", "2100"),
            ("year_count", "78"),
            ("trajectories", "1000"),
            ("locations", "236"),
            ("tfr_shift_count", "2"),
            ("e0_female_shift_count", "2"),
            ("e0_male_shift_count", "2"),
            ("accessor_shifts_applied", "true"),
        ):
            writer.writerow(row)
    return source_codes


def _write_crosswalk(path, source_codes):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("loc_id", "name"))
        for code in source_codes:
            writer.writerow((code, "Finland" if code == 246 else f"Location {code}"))
        writer.writerow((336, "Holy See"))


def test_accessor_export_validates_and_becomes_2024_forward_draws(tmp_path):
    export_dir = tmp_path / "export"
    source_codes = _write_source_export(export_dir)
    crosswalk = tmp_path / "crosswalk.csv"
    _write_crosswalk(crosswalk, source_codes)
    metadata = export_uw_fixture._build_metadata(
        export_dir,
        archive_sha256={"tfr_annual": "a" * 64, "e0_annual": "b" * 64},
        country_code=246,
        iso3="FIN",
    )
    (export_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    source = uw.validate_uw_export(export_dir, crosswalk_path=crosswalk)
    assert len(source) == 1000
    assert source.years.tolist() == list(range(2023, 2101))
    assert source.tfr.shape == (78, 1000)
    assert not source.tfr.flags.writeable

    first = next(iter(source))
    assert first.draw_id == "uw-wpp2024-0001"
    assert first.locations == ("FIN",)
    assert first.years.tolist() == list(range(2024, 2101))
    assert first.tfr.shape == (77, 1)
    assert first.tfr[0, 0] == pytest.approx(1.40002)
    assert source.tfr[0, 0] == pytest.approx(1.40001)  # retained 2023 anchor
    assert first.provenance.fertility_draw_id == "tfr-trajectory-1"
    assert first.provenance.mortality_draw_id == "joint-e0-trajectory-1"
    assert "not document" in first.provenance.coupling_method


def test_file_fingerprint_failure_precedes_data_use(tmp_path):
    export_dir = tmp_path / "export"
    source_codes = _write_source_export(export_dir)
    crosswalk = tmp_path / "crosswalk.csv"
    _write_crosswalk(crosswalk, source_codes)
    metadata = export_uw_fixture._build_metadata(
        export_dir,
        archive_sha256={"tfr_annual": "a" * 64, "e0_annual": "b" * 64},
        country_code=246,
        iso3="FIN",
    )
    (export_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (export_dir / "session-info.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(uw.UwExportError, match="session-info.txt does not match"):
        uw.validate_uw_export(export_dir, crosswalk_path=crosswalk)

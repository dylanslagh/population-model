"""Validate UW's R-accessor export and expose compact trajectory draws.

R is used only at the native-object boundary.  Everything accepted by this
module is plain, checksummed CSV plus metadata, with the 2023 source anchor
kept in the export and deliberately removed from the model's 2024-forward
rate years.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from popmodel import paths
from popmodel.bayes import TrajectoryDraw, TrajectoryProvenance
from popmodel.sources import fetch, uw_wpp2024

EXPORT_SCHEMA_VERSION = 1
EXPECTED_R_VERSION = "4.4.2"
EXPECTED_PACKAGES = {"bayesTFR": "7.4-4", "bayesLife": "5.3-0"}
EXPECTED_R_REPOSITORY = "https://packagemanager.posit.co/cran/2024-11-11"
EXPECTED_PACKAGE_REVISIONS = {
    "bayesTFR": "9c7116a00e8f6cb59956c859bee6659b65a574a4",
    "bayesLife": "94780a40847a319b81e3c4dd4a01fa3b58dd733e",
}
EXPECTED_PACKAGE_SOURCES = {
    "bayesTFR": (
        "https://github.com/PPgp/bayesTFR/archive/"
        f"{EXPECTED_PACKAGE_REVISIONS['bayesTFR']}.tar.gz"
    ),
    "bayesLife": (
        "https://github.com/PPgp/bayesLife/archive/"
        f"{EXPECTED_PACKAGE_REVISIONS['bayesLife']}.tar.gz"
    ),
}
EXPECTED_PACKAGE_SOURCE_SHA256 = {
    "bayesTFR": "8acec2ccf4c0c66f3bbbd23559d5bd13b44aaba48bae700113f4fbc760b91d58",
    "bayesLife": "30cb9601ad8bc0c9e080a07de34e1b8769206295e153fa1c308c2ca5fa6084e1",
}
EXPECTED_ACCESSORS = (
    "bayesTFR::get.tfr.prediction",
    "bayesTFR::get.tfr.trajectories",
    "bayesLife::get.e0.prediction",
    "bayesLife::get.e0.jmale.prediction",
    "bayesLife::get.e0.trajectories",
)
COUPLING_METHOD = (
    "UW female and male e0 use the joint life-expectancy model; TFR and joint "
    "e0 are paired by equal one-based trajectory index for reproducibility. "
    "UW does not document this as a joint fertility-mortality posterior."
)
TRAJECTORY_COLUMNS = (
    "loc_id", "country", "iso3", "year", "trajectory_id",
    "tfr", "e0_female", "e0_male",
)


class UwExportError(RuntimeError):
    """An exported value or its provenance is incomplete or inconsistent."""


def _readonly(value, dtype=None) -> np.ndarray:
    out = np.asarray(value, dtype=dtype).copy()
    out.setflags(write=False)
    return out


def _require(mapping: dict, key: str, context: str):
    if key not in mapping:
        raise UwExportError(f"{context} is missing {key!r}")
    return mapping[key]


def _read_locations(path: Path) -> tuple[tuple[int, ...], dict[int, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != ("loc_id", "name"):
                raise UwExportError("locations.csv must have columns loc_id,name")
            rows = list(reader)
    except FileNotFoundError as exc:
        raise UwExportError("locations.csv is missing") from exc
    codes: list[int] = []
    names: dict[int, str] = {}
    for row in rows:
        try:
            code = int(row["loc_id"])
        except (TypeError, ValueError) as exc:
            raise UwExportError("locations.csv contains a non-integer LocID") from exc
        name = str(row["name"]).strip()
        if not name:
            raise UwExportError(f"location {code} has no name")
        if code in names:
            raise UwExportError(f"locations.csv repeats LocID {code}")
        codes.append(code)
        names[code] = name
    if len(codes) != uw_wpp2024.EXPECTED_LOCATIONS:
        raise UwExportError(
            f"expected {uw_wpp2024.EXPECTED_LOCATIONS} UW locations, found "
            f"{len(codes)}"
        )
    return tuple(codes), names


def _read_wpp_crosswalk(path: Path) -> dict[int, str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "loc_id" not in (reader.fieldnames or ()) or "name" not in (
                reader.fieldnames or ()
            ):
                raise UwExportError("WPP crosswalk must contain loc_id and name")
            result = {int(row["loc_id"]): str(row["name"]).strip() for row in reader}
    except FileNotFoundError as exc:
        raise UwExportError(f"WPP crosswalk is missing: {path}") from exc
    if len(result) != 237:
        raise UwExportError(f"expected 237 WPP locations in the crosswalk, found {len(result)}")
    return result


@dataclass(frozen=True)
class UwOneCountryExport:
    """One fully validated source export, including its non-model anchor year."""

    directory: Path
    metadata: dict
    loc_id: int
    iso3: str
    country: str
    years: np.ndarray  # 2023..2100, including the source anchor
    trajectory_ids: np.ndarray  # 1..1000
    tfr: np.ndarray  # (78, 1000)
    e0_female: np.ndarray  # (78, 1000)
    e0_male: np.ndarray  # (78, 1000)

    def __len__(self) -> int:
        return len(self.trajectory_ids)

    def __iter__(self) -> Iterator[TrajectoryDraw]:
        forecast = self.years >= uw_wpp2024.FORECAST_START
        years = self.years[forecast]
        archive_hashes = self.metadata["archive_sha256"]
        for column, trajectory_id in enumerate(self.trajectory_ids):
            number = int(trajectory_id)
            provenance = TrajectoryProvenance(
                source_revision=uw_wpp2024.REVISION_LABEL,
                fertility_source=(
                    "UW annual TFR archive, accessor-adjusted; SHA-256 "
                    f"{archive_hashes['tfr_annual']}"
                ),
                mortality_source=(
                    "UW annual joint female/male e0 archive, accessor-adjusted; "
                    f"SHA-256 {archive_hashes['e0_annual']}"
                ),
                fertility_draw_id=f"tfr-trajectory-{number}",
                mortality_draw_id=f"joint-e0-trajectory-{number}",
                coupling_method=COUPLING_METHOD,
            )
            yield TrajectoryDraw(
                draw_id=f"uw-wpp2024-{number:04d}",
                years=years,
                locations=(self.iso3,),
                tfr=self.tfr[forecast, column : column + 1],
                e0_female=self.e0_female[forecast, column : column + 1],
                e0_male=self.e0_male[forecast, column : column + 1],
                draw_kind="posterior",
                weight=1.0,
                provenance=provenance,
            )


def validate_uw_export(
    directory: Path,
    *,
    crosswalk_path: Path | None = None,
) -> UwOneCountryExport:
    """Validate a complete one-country export and return its draw source."""
    directory = Path(directory)
    metadata_path = directory / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UwExportError("metadata.json is missing") from exc
    except json.JSONDecodeError as exc:
        raise UwExportError("metadata.json is not valid JSON") from exc

    if _require(metadata, "schema_version", "metadata") != EXPORT_SCHEMA_VERSION:
        raise UwExportError("unsupported UW export schema version")
    if _require(metadata, "source_revision", "metadata") != uw_wpp2024.REVISION:
        raise UwExportError("export source revision is not UW_WPP2024")
    if _require(metadata, "R_version", "metadata") != EXPECTED_R_VERSION:
        raise UwExportError(f"UW export must use R {EXPECTED_R_VERSION}")
    packages = _require(metadata, "packages", "metadata")
    if packages != EXPECTED_PACKAGES:
        raise UwExportError(
            f"UW export packages must be {EXPECTED_PACKAGES}, found {packages}"
        )
    if _require(metadata, "R_repository_snapshot", "metadata") != (
        EXPECTED_R_REPOSITORY
    ):
        raise UwExportError("UW export dependency repository is not date-pinned")
    if _require(metadata, "package_sources", "metadata") != EXPECTED_PACKAGE_SOURCES:
        raise UwExportError("UW export package-source provenance is wrong")
    if _require(metadata, "package_source_revisions", "metadata") != (
        EXPECTED_PACKAGE_REVISIONS
    ):
        raise UwExportError("UW export package-source revisions are wrong")
    if _require(metadata, "package_source_sha256", "metadata") != (
        EXPECTED_PACKAGE_SOURCE_SHA256
    ):
        raise UwExportError("UW export package-source fingerprints are wrong")
    if tuple(_require(metadata, "accessors", "metadata")) != EXPECTED_ACCESSORS:
        raise UwExportError("UW export did not use the required public accessors")
    if _require(metadata, "coupling_method", "metadata") != COUPLING_METHOD:
        raise UwExportError("UW export does not state the required coupling limitation")

    country = _require(metadata, "country", "metadata")
    loc_id = int(_require(country, "loc_id", "country metadata"))
    iso3 = str(_require(country, "iso3", "country metadata")).strip()
    country_name = str(_require(country, "name", "country metadata")).strip()
    if len(iso3) != 3 or not country_name:
        raise UwExportError("country ISO3 and name must be present")

    year_info = _require(metadata, "years", "metadata")
    expected_years = np.arange(
        uw_wpp2024.TRAJECTORY_ANCHOR_YEAR, uw_wpp2024.FORECAST_END + 1
    )
    expected_year_metadata = {
        "source_start": uw_wpp2024.TRAJECTORY_ANCHOR_YEAR,
        "forecast_start": uw_wpp2024.FORECAST_START,
        "end": uw_wpp2024.FORECAST_END,
        "count": len(expected_years),
    }
    if year_info != expected_year_metadata:
        raise UwExportError(
            f"source years must be {expected_year_metadata}, found {year_info}"
        )
    if _require(metadata, "trajectories", "metadata") != (
        uw_wpp2024.EXPECTED_TRAJECTORIES
    ):
        raise UwExportError("UW export must contain all 1,000 trajectories")
    if _require(metadata, "shape", "metadata") != [
        len(expected_years), uw_wpp2024.EXPECTED_TRAJECTORIES
    ]:
        raise UwExportError("UW export shape metadata is wrong")

    hashes = _require(metadata, "file_sha256", "metadata")
    for filename in (
        "trajectories.csv", "locations.csv", "shifts.csv", "session-info.txt",
        "r-metadata.tsv",
    ):
        path = directory / filename
        if not path.is_file():
            raise UwExportError(f"{filename} is missing")
        expected_hash = hashes.get(filename)
        if expected_hash is None or fetch.sha256_of(path) != expected_hash:
            raise UwExportError(f"{filename} does not match metadata.json")
    archive_hashes = _require(metadata, "archive_sha256", "metadata")
    if set(archive_hashes) != set(uw_wpp2024.REQUIRED_KEYS) or any(
        len(str(value)) != 64
        or any(character not in "0123456789abcdef" for character in str(value).lower())
        for value in archive_hashes.values()
    ):
        raise UwExportError("archive SHA-256 provenance is incomplete")

    location_codes, location_names = _read_locations(directory / "locations.csv")
    if set(location_codes) != set(location_names):
        raise UwExportError("location code/name table is inconsistent")
    wpp = _read_wpp_crosswalk(crosswalk_path or paths.REFERENCE / "crosswalk.csv")
    missing = set(wpp) - set(location_codes)
    extra = set(location_codes) - set(wpp)
    if missing != {336} or extra:
        raise UwExportError(
            "UW/WPP location reconciliation must leave only Holy See (LocID 336); "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if "holy see" not in wpp[336].lower():
        raise UwExportError("LocID 336 is not labelled Holy See in the WPP crosswalk")
    reconciliation = _require(metadata, "location_reconciliation", "metadata")
    if reconciliation != {
        "uw_count": uw_wpp2024.EXPECTED_LOCATIONS,
        "wpp_count": 237,
        "missing_wpp_loc_ids": [336],
    }:
        raise UwExportError("metadata does not record the exact UW/WPP reconciliation")
    if loc_id not in location_names:
        raise UwExportError(f"exported country LocID {loc_id} is absent from locations.csv")

    shift_metadata = _require(metadata, "alignment_shifts", "metadata")
    expected_components = {"tfr", "e0_female", "e0_male"}
    if set(shift_metadata) != expected_components:
        raise UwExportError("alignment-shift metadata must cover TFR and both e0 sexes")
    shift_counts = {component: 0 for component in expected_components}
    with (directory / "shifts.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("component", "shift_index", "value"):
            raise UwExportError(
                "shifts.csv must have columns component,shift_index,value"
            )
        for row in reader:
            component = row["component"]
            if component not in expected_components:
                raise UwExportError(f"unknown shift component {component!r}")
            shift_counts[component] += 1
            try:
                index = int(row["shift_index"])
                value = float(row["value"])
            except (TypeError, ValueError) as exc:
                raise UwExportError("shifts.csv contains an invalid number") from exc
            if index != shift_counts[component] or not np.isfinite(value):
                raise UwExportError(
                    f"{component} shift indices must be consecutive and finite"
                )
    for component, count in shift_counts.items():
        if count <= 0 or shift_metadata[component] != {
            "stored": True, "count": count, "applied_by_accessor": True
        }:
            raise UwExportError(f"alignment-shift metadata is wrong for {component}")

    trajectory_path = directory / "trajectories.csv"
    n_years = len(expected_years)
    n_draws = uw_wpp2024.EXPECTED_TRAJECTORIES
    tfr = np.empty((n_years, n_draws), dtype=np.float64)
    e0_female = np.empty_like(tfr)
    e0_male = np.empty_like(tfr)
    expected_rows = n_years * n_draws
    row_count = 0
    with trajectory_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != TRAJECTORY_COLUMNS:
            raise UwExportError(
                "trajectories.csv columns must be " + ",".join(TRAJECTORY_COLUMNS)
            )
        for row_count, row in enumerate(reader, start=1):
            zero = row_count - 1
            column, year_index = divmod(zero, n_years)
            if column >= n_draws:
                raise UwExportError("trajectories.csv has more than 78,000 rows")
            expected_id = column + 1
            expected_year = int(expected_years[year_index])
            try:
                actual = (
                    int(row["loc_id"]), int(row["year"]), int(row["trajectory_id"])
                )
                values = tuple(float(row[name]) for name in (
                    "tfr", "e0_female", "e0_male"
                ))
            except (TypeError, ValueError) as exc:
                raise UwExportError(
                    f"trajectories.csv row {row_count} contains an invalid number"
                ) from exc
            if actual != (loc_id, expected_year, expected_id):
                raise UwExportError(
                    f"trajectories.csv row {row_count} is out of canonical order; "
                    f"expected {(loc_id, expected_year, expected_id)}, found {actual}"
                )
            if row["country"] != country_name or row["iso3"] != iso3:
                raise UwExportError(
                    f"trajectories.csv row {row_count} has different country identity"
                )
            if not np.all(np.isfinite(values)):
                raise UwExportError(f"trajectories.csv row {row_count} is non-finite")
            if not 0 < values[0] <= 15:
                raise UwExportError(f"implausible TFR at trajectories.csv row {row_count}")
            if not 0 < values[1] <= 130 or not 0 < values[2] <= 130:
                raise UwExportError(f"implausible e0 at trajectories.csv row {row_count}")
            tfr[year_index, column], e0_female[year_index, column], e0_male[
                year_index, column
            ] = values
    if row_count != expected_rows:
        raise UwExportError(
            f"trajectories.csv must have {expected_rows:,} rows, found {row_count:,}"
        )

    return UwOneCountryExport(
        directory=directory,
        metadata=metadata,
        loc_id=loc_id,
        iso3=iso3,
        country=country_name,
        years=_readonly(expected_years, np.int64),
        trajectory_ids=_readonly(np.arange(1, n_draws + 1), np.int64),
        tfr=_readonly(tfr),
        e0_female=_readonly(e0_female),
        e0_male=_readonly(e0_male),
    )

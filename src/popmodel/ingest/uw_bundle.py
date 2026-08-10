"""All 236 validated UW exports, compacted into one array bundle.

The per-country CSV exports are the evidence: full precision, one directory per
country, each with its own checksums and R session record. They are not a
convenient thing to read 1,000 times. This module turns them into a single
array file once, exactly as `ingest/wpp.py` does for the UN's CSVs, and records
which exports went into it.

The cross-country pairing assumption
------------------------------------
The ensemble needs, for each draw, one internally consistent world: Nigeria and
Finland at the same time. That means deciding what trajectory number 7 in
Nigeria has to do with trajectory number 7 in Finland.

They are paired by index, and the reason is that bayesTFR and bayesLife
generate a country's trajectories from posterior samples that also carry the
world-level and region-level parameters. Trajectory *k* across countries
therefore comes from a shared posterior state rather than from independent
resampling, which is what makes summing them to a world total meaningful, and
it is how `bayesPop` produces its own aggregates.

This is stated, and travels with every draw, because it is doing real work: if
the pairing were wrong, the world total's spread would be wrong even though
every country's own spread stayed right. **It is inferred from how the packages
are built and used, not from a line of UW documentation that says so.** Treat
it as the bundle's most load-bearing unverified assumption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from popmodel import paths
from popmodel.bayes import TrajectoryDraw, TrajectoryProvenance
from popmodel.ingest import uw
from popmodel.sources import uw_wpp2024

BUNDLE_VERSION = 1

CROSS_COUNTRY_PAIRING = (
    "countries are paired by trajectory index: trajectory k in every country "
    "comes from the same posterior sample, which carries the shared world and "
    "region parameters. Inferred from how bayesTFR/bayesLife generate and "
    "bayesPop aggregates trajectories, not from explicit UW documentation."
)


class UwBundleError(RuntimeError):
    """The compacted bundle is missing, stale, or internally inconsistent."""


def bundle_path() -> Path:
    return paths.PROCESSED / "uw_wpp2024_draws.npz"


@dataclass(frozen=True)
class UwDrawBundle:
    """Every UW location and trajectory, ready to iterate as world-wide draws."""

    years: np.ndarray  # (78,) 2023..2100, including the non-model anchor
    iso3: tuple[str, ...]  # (L,)
    loc_id: np.ndarray  # (L,)
    trajectory_ids: np.ndarray  # (1000,)
    tfr: np.ndarray  # (78, L, 1000)
    e0_female: np.ndarray
    e0_male: np.ndarray
    provenance: dict

    @property
    def n_draws(self) -> int:
        return len(self.trajectory_ids)

    def forecast_mask(self) -> np.ndarray:
        """The model years. The 2023 anchor is source evidence, not a forecast."""
        return self.years >= uw_wpp2024.FORECAST_START

    def __iter__(self) -> Iterator[TrajectoryDraw]:
        """One draw per trajectory, carrying every country at once."""
        forecast = self.forecast_mask()
        years = self.years[forecast]
        archive = self.provenance["archive_sha256"]
        for column, trajectory_id in enumerate(self.trajectory_ids):
            number = int(trajectory_id)
            provenance = TrajectoryProvenance(
                source_revision=uw_wpp2024.REVISION_LABEL,
                fertility_source=(
                    "UW annual TFR archive, accessor-adjusted; SHA-256 "
                    f"{archive['tfr_annual']}"
                ),
                mortality_source=(
                    "UW annual joint female/male e0 archive, accessor-adjusted; "
                    f"SHA-256 {archive['e0_annual']}"
                ),
                fertility_draw_id=f"tfr-trajectory-{number}",
                mortality_draw_id=f"joint-e0-trajectory-{number}",
                coupling_method=f"{uw.COUPLING_METHOD} {CROSS_COUNTRY_PAIRING}",
            )
            yield TrajectoryDraw(
                draw_id=f"uw-wpp2024-{number:04d}",
                years=years,
                locations=self.iso3,
                tfr=self.tfr[forecast, :, column],
                e0_female=self.e0_female[forecast, :, column],
                e0_male=self.e0_male[forecast, :, column],
                draw_kind="posterior",
                weight=1.0,
                provenance=provenance,
            )


def build(export_root: Path | None = None) -> UwDrawBundle:
    """Validate every country export and stack them into one bundle.

    Every directory goes through the same `validate_uw_export` the single
    country fixture does, so nothing enters the bundle that has not had its
    checksums, provenance and value bounds checked.
    """
    export_root = export_root or (paths.INTERIM / uw_wpp2024.REVISION / "exports")
    directories = sorted(
        (d for d in export_root.glob("*") if d.is_dir() and d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    if len(directories) != uw_wpp2024.EXPECTED_LOCATIONS:
        raise UwBundleError(
            f"expected {uw_wpp2024.EXPECTED_LOCATIONS} country exports under "
            f"{export_root}, found {len(directories)}\n"
            f"  Run:  python scripts/export_uw_all.py --rscript <Rscript.exe>"
        )

    exports = [uw.validate_uw_export(directory) for directory in directories]
    first = exports[0]
    n_years = len(first.years)
    n_draws = len(first.trajectory_ids)
    n_loc = len(exports)

    tfr = np.empty((n_years, n_loc, n_draws), dtype=np.float64)
    e0_female = np.empty_like(tfr)
    e0_male = np.empty_like(tfr)
    archive_hashes: set[tuple] = set()

    for index, export in enumerate(exports):
        if not np.array_equal(export.years, first.years):
            raise UwBundleError(f"{export.iso3} covers different years")
        if not np.array_equal(export.trajectory_ids, first.trajectory_ids):
            raise UwBundleError(f"{export.iso3} has different trajectory ids")
        tfr[:, index, :] = export.tfr
        e0_female[:, index, :] = export.e0_female
        e0_male[:, index, :] = export.e0_male
        archive_hashes.add(tuple(sorted(export.metadata["archive_sha256"].items())))

    if len(archive_hashes) != 1:
        raise UwBundleError(
            "country exports came from different source archives; rebuild them all"
        )

    iso3 = tuple(export.iso3 for export in exports)
    if len(set(iso3)) != len(iso3):
        raise UwBundleError("two country exports claim the same ISO3 code")

    provenance = {
        "bundle_version": BUNDLE_VERSION,
        "source_revision": uw_wpp2024.REVISION,
        "source_label": uw_wpp2024.REVISION_LABEL,
        "locations": n_loc,
        "trajectories": n_draws,
        "years": [int(first.years[0]), int(first.years[-1])],
        "forecast_start": uw_wpp2024.FORECAST_START,
        "archive_sha256": dict(next(iter(archive_hashes))),
        "cross_country_pairing": CROSS_COUNTRY_PAIRING,
        "exports": [
            {
                "loc_id": export.loc_id,
                "iso3": export.iso3,
                "trajectories_sha256": export.metadata["file_sha256"][
                    "trajectories.csv"
                ],
            }
            for export in exports
        ],
    }

    return UwDrawBundle(
        years=first.years,
        iso3=iso3,
        loc_id=np.array([export.loc_id for export in exports], dtype=np.int64),
        trajectory_ids=first.trajectory_ids,
        tfr=tfr,
        e0_female=e0_female,
        e0_male=e0_male,
        provenance=provenance,
    )


def save(bundle: UwDrawBundle, path: Path | None = None) -> Path:
    path = path or bundle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        years=bundle.years,
        iso3=np.array(bundle.iso3),
        loc_id=bundle.loc_id,
        trajectory_ids=bundle.trajectory_ids,
        tfr=bundle.tfr,
        e0_female=bundle.e0_female,
        e0_male=bundle.e0_male,
    )
    path.with_suffix(".json").write_text(
        json.dumps(bundle.provenance, indent=2) + "\n", encoding="utf-8"
    )
    return path


def load(path: Path | None = None) -> UwDrawBundle:
    path = path or bundle_path()
    if not path.exists():
        raise UwBundleError(
            f"{path.name} has not been built.\n"
            f"  Run:  python scripts/build_uw_bundle.py"
        )
    z = np.load(path, allow_pickle=False)
    provenance = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if provenance.get("bundle_version") != BUNDLE_VERSION:
        raise UwBundleError("the stored UW draw bundle is a different version")
    return UwDrawBundle(
        years=z["years"],
        iso3=tuple(str(code) for code in z["iso3"]),
        loc_id=z["loc_id"],
        trajectory_ids=z["trajectory_ids"],
        tfr=z["tfr"],
        e0_female=z["e0_female"],
        e0_male=z["e0_male"],
        provenance=provenance,
    )

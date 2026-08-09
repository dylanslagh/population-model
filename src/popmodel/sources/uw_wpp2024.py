"""UW Bayesian trajectories aligned to WPP 2024.

These are University of Washington products, not UN products. The distinction
matters: UW used the bayesTFR and bayesLife models and shifted predictive means
to the published WPP 2024 medium series, but the resulting draws are not the
UN's official probabilistic files.

The archives are native, directory-backed R simulation objects. Read them with
the pinned package accessors or official converters; directly opening selected
``.rda`` files can miss accessor-applied shifts and draw metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

REVISION = "UW_WPP2024"
REVISION_LABEL = "UW Bayesian annual trajectories aligned to WPP 2024"
SOURCE_PAGE = "https://bayespop.csss.washington.edu/download/"
VIGNETTE = (
    "https://bayespop.csss.washington.edu/bayesPop/vignettes/"
    "population-projections.html"
)
URLS_VERIFIED_ON = "2026-08-09"

EXPECTED_TRAJECTORIES = 1_000
EXPECTED_LOCATIONS = 236
TRAJECTORY_ANCHOR_YEAR = 2023
FORECAST_START = 2024
FORECAST_END = 2100
LOCATION_RECONCILIATION = (
    "WPP 2024 contains 237 countries and areas, while these UW trajectories contain "
    "236. The likely exclusion is Holy See (M49 336), the only location below 1,000 "
    "people in 2023; verify this against extracted LocIDs before conversion."
)


@dataclass(frozen=True)
class UwArchive:
    key: str
    filename: str
    url: str
    purpose: str
    expected_bytes: int
    package: str
    package_version: str
    unpacked_sim_dir: str
    creation_script_url: str
    etag_when_verified: str
    last_modified_when_verified: str


ARCHIVES: dict[str, UwArchive] = {
    archive.key: archive
    for archive in (
        UwArchive(
            key="tfr_annual",
            filename="TFR1simWPP2024.tgz",
            url=(
                "https://bayespop.csss.washington.edu/data/bayesTFR/"
                "TFR1simWPP2024.tgz"
            ),
            purpose=(
                "1,000 annual total-fertility trajectories, including uncertainty "
                "around annual estimates and projections through 2100. Predictive "
                "means are shifted to WPP 2024 medium values."
            ),
            expected_bytes=1_808_601_202,
            package="bayesTFR",
            package_version="7.4-4",
            unpacked_sim_dir="TFR1unc/sim20241101",
            creation_script_url=(
                "https://bayespop.csss.washington.edu/data/bayesTFR/"
                "TFRsimWPP2024/TFR1unc/README.r"
            ),
            etag_when_verified='"6bcd1072-6264750cda46c"',
            last_modified_when_verified="2024-11-07T00:00:00Z",
        ),
        UwArchive(
            key="e0_annual",
            filename="e01simWPP2024.tgz",
            url=(
                "https://bayespop.csss.washington.edu/data/bayesLife/"
                "e01simWPP2024.tgz"
            ),
            purpose=(
                "1,000 paired female/male annual life-expectancy trajectories "
                "through 2100. Predictive means are shifted to WPP 2024 medium "
                "values."
            ),
            expected_bytes=435_101_297,
            package="bayesLife",
            package_version="5.3-0",
            unpacked_sim_dir="e01/sim20241101",
            creation_script_url=(
                "https://bayespop.csss.washington.edu/data/bayesLife/"
                "WPP2024/e01/README.r"
            ),
            etag_when_verified='"19ef1e71-62647614df90d"',
            last_modified_when_verified="2024-11-07T00:04:37Z",
        ),
    )
}

REQUIRED_KEYS = list(ARCHIVES)

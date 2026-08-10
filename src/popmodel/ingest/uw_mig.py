"""UW's Bayesian net migration trajectories, turned into engine migration.

The fertility and mortality archives carry no migration, so without this the
ensemble runs at zero migration -- fine for a world total, badly wrong for the
Gulf states and the small island states. UW publishes migration separately, from
`bayesMig`: the Azose and Raftery (2015) hierarchical model, 1,000 annual
trajectories for the same 236 countries, adjusted so its means align with WPP
2024's medium projection.

What the source gives, and what the engine needs
------------------------------------------------
The source is one number per country, year and trajectory: a net migration
**rate**. The engine needs net migrants by single year of age and sex. Three
separate decisions bridge that, and each one is stated here because each one
changes the answer.

**1. The rate's denominator is population.** Not documented in the archive, so
it was checked: the median 2024 rate multiplied by that country's 1 January
population reproduces WPP's own published net migration figures -- the United
States to 0.2%, India 0.3%, China 0.7%, Canada 0.5%. Small countries scatter
more, up to about 15%, which is expected because bayesMig aligns its *means* to
WPP while this compares *medians*. Mid-year population would be marginally more
correct than 1 January; the difference is far below the scatter.

**2. The level is the median trajectory, not one per draw.** The engine takes
one shared migration path per ensemble, so the ensemble's spread reflects
fertility and mortality uncertainty and not migration uncertainty. Pairing
migration trajectory *k* with fertility trajectory *k* would be a third
undocumented index coupling across three separately fitted models, so the
narrower band is the more honest of the two options. Say so wherever it is
published.

**3. The age and sex composition is borrowed, and is not evidence.** Nobody
publishes net migrants by single year of age. The composition here is the
UN's own migration residual -- what has to be added to the UN's medium path to
make it balance -- normalised per country over the absolute flows, so it
survives countries whose net migration is near zero while their gross flows are
not. The level is UW's; the shape is the UN's residual; the residual is not an
independent estimate of anything. The result is therefore labelled a scenario
knob, which is what the `MigrationAssumption` contract requires.

Counts are computed against the UN's medium population path rather than each
draw's own evolving population, because the engine takes migration as a fixed
array. Draws far from the median therefore carry very slightly the wrong
counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from popmodel import paths
from popmodel.bayes import MigrationAssumption, SeriesExtension
from popmodel.engine import cohort

TRAJECTORY_COLUMNS = ("LocID", "Period", "Year", "Trajectory", "Mig")
EXPECTED_LOCATIONS = 236
EXPECTED_TRAJECTORIES = 1000
ANCHOR_YEAR = 2023
FORECAST_START = 2024
FORECAST_END = 2100

#: Net migration rates outside this range are not credible for a whole country
#: in a single year and mean the file is not what it is believed to be.
RATE_LIMIT = 0.5

SOURCE_LABEL = (
    "UW bayesMig annual net-migration-rate trajectories aligned to WPP 2024 "
    "(Azose and Raftery 2015)"
)
SCENARIO_KNOB = (
    "net migration: level from UW's median bayesMig trajectory, age and sex "
    "composition borrowed from the UN's own migration residual, which is not "
    "an independent estimate; migration uncertainty is excluded because the "
    "ensemble takes one shared migration path"
)


class MigrationIngestError(RuntimeError):
    """The migration source is missing, malformed, or not what it claims."""


def bundle_path() -> Path:
    return paths.PROCESSED / "uw_wpp2024_migration.npz"


@dataclass(frozen=True)
class MigrationRates:
    """Median net migration rates by year and country, with their provenance."""

    years: np.ndarray  # (T,)
    loc_id: np.ndarray  # (L,)
    rates: np.ndarray  # (T, L) net migrants per person per year
    provenance: dict


def read_trajectories(csv_path: Path) -> MigrationRates:
    """Read the ASCII trajectory export and reduce it to median rates.

    Only the median is retained. Keeping all 1,000 would imply the ensemble can
    use them, and it cannot -- see the module docstring.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise MigrationIngestError(f"migration trajectories not found: {csv_path}")

    frame = pd.read_csv(
        csv_path,
        usecols=["LocID", "Year", "Trajectory", "Mig"],
        dtype={"LocID": "int32", "Year": "int32", "Trajectory": "int32", "Mig": "float64"},
    )
    locations = np.sort(frame["LocID"].unique())
    years = np.sort(frame["Year"].unique())
    trajectories = frame["Trajectory"].nunique()

    if len(locations) != EXPECTED_LOCATIONS:
        raise MigrationIngestError(
            f"expected {EXPECTED_LOCATIONS} locations, found {len(locations)}"
        )
    if trajectories != EXPECTED_TRAJECTORIES:
        raise MigrationIngestError(
            f"expected {EXPECTED_TRAJECTORIES} trajectories, found {trajectories}"
        )
    expected_years = np.arange(ANCHOR_YEAR, FORECAST_END + 1)
    if not np.array_equal(years, expected_years):
        raise MigrationIngestError(
            f"expected years {ANCHOR_YEAR}-{FORECAST_END}, found "
            f"{years.min()}-{years.max()}"
        )
    if len(frame) != len(locations) * len(years) * trajectories:
        raise MigrationIngestError("the migration grid is not complete")
    if not np.all(np.isfinite(frame["Mig"])):
        raise MigrationIngestError("migration rates contain non-finite values")
    extreme = np.abs(frame["Mig"]) > RATE_LIMIT
    if extreme.any():
        worst = float(frame["Mig"][extreme].abs().max())
        raise MigrationIngestError(
            f"a net migration rate of {worst:.3f} is outside the plausible "
            f"range +/-{RATE_LIMIT}; this file is probably not annual rates"
        )

    grid = (
        frame.groupby(["Year", "LocID"])["Mig"].median().unstack().loc[years, locations]
    )
    provenance = {
        "source_label": SOURCE_LABEL,
        "model": "Azose and Raftery (2015), bayesMig",
        "trajectories_in_source": int(trajectories),
        "reduction": "median across trajectories, per country and year",
        "locations": int(len(locations)),
        "years": [int(years[0]), int(years[-1])],
        "units": "net migrants per person per year",
    }
    return MigrationRates(
        years=np.asarray(years, dtype=np.int64),
        loc_id=np.asarray(locations, dtype=np.int64),
        rates=np.ascontiguousarray(grid.to_numpy(dtype=np.float64)),
        provenance=provenance,
    )


def age_sex_composition(residual: np.ndarray) -> np.ndarray:
    """Per-country age and sex shares of migrants, from the UN's residual.

    Args:
        residual: (T, L, 2, 101) net migrants by age backed out of the UN's
            medium path.

    Returns:
        (L, 2, 101) non-negative shares summing to one for each country.

    Normalised over **absolute** flows across all years, so a country whose net
    migration is near zero while its gross flows are not still gets a usable
    composition instead of a division by almost nothing.
    """
    residual = np.asarray(residual, dtype=np.float64)
    if residual.ndim != 4 or residual.shape[2:] != (cohort.N_SEXES, cohort.N_AGES):
        raise MigrationIngestError(
            f"migration residual must be (T, L, 2, {cohort.N_AGES}); got {residual.shape}"
        )
    gross = np.abs(residual).sum(axis=0)  # (L, 2, 101)
    total = gross.sum(axis=(1, 2), keepdims=True)
    if np.any(total <= 0):
        empty = int(np.count_nonzero(total <= 0))
        raise MigrationIngestError(
            f"{empty} country/countries have no migration residual at all, so "
            f"they carry no age composition to borrow"
        )
    return gross / total


def build_assumption(
    rates: MigrationRates,
    *,
    composition: np.ndarray,
    population: np.ndarray,
    loc_id: np.ndarray,
    locations: tuple[str, ...],
    years: np.ndarray,
) -> MigrationAssumption:
    """Turn median rates plus a borrowed age composition into engine migration.

    Args:
        rates: median net migration rates from the UW source.
        composition: (L, 2, 101) age and sex shares, in `locations` order.
        population: (T, L) total population per year on the UN's medium path.
        loc_id: (L,) UN codes matching `locations`.
        locations: ISO3 codes, the order everything downstream uses.
        years: (T,) the projection's rate years.
    """
    order = {int(code): i for i, code in enumerate(rates.loc_id)}
    missing = [int(code) for code in loc_id if int(code) not in order]
    if missing:
        raise MigrationIngestError(
            f"the migration source has no trajectories for LocID(s): {missing[:5]}"
        )
    columns = np.array([order[int(code)] for code in loc_id])

    first = int(rates.years[0])
    rows = np.asarray(years, dtype=np.int64) - first
    if np.any(rows < 0):
        raise MigrationIngestError("migration rates start after the projection does")
    # Past the source's final year the last rate is held, which the assumption
    # records as its extension policy rather than leaving implicit.
    rows = np.minimum(rows, len(rates.years) - 1)

    rate_grid = rates.rates[np.ix_(rows, columns)]  # (T, L)
    if population.shape != rate_grid.shape:
        raise MigrationIngestError(
            f"population {population.shape} does not match rates {rate_grid.shape}"
        )
    net = rate_grid * population  # (T, L) people
    values = net[:, :, None, None] * composition[None, :, :, :]

    return MigrationAssumption(
        years=years,
        locations=locations,
        values=values,
        source=(
            f"{SOURCE_LABEL}; median trajectory, rate applied to the UN medium "
            f"population path, age and sex composition from the UN's own "
            f"migration residual"
        ),
        independently_sourced=False,
        extension=SeriesExtension.hold_last(
            "UW's migration trajectories end in 2100 and this projection runs "
            "further; the final year's net migrants are held constant"
        ),
        scenario_knob=SCENARIO_KNOB,
    )


def save(
    rates: MigrationRates,
    composition: np.ndarray,
    locations,
    population: np.ndarray,
    population_years: np.ndarray,
    path=None,
) -> Path:
    """Store the rates, the borrowed composition, and the denominator.

    The UN medium population path is stored too, because turning a rate into a
    count needs it and reading it back out of the raw CSVs takes minutes.
    """
    path = path or bundle_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        years=rates.years,
        loc_id=rates.loc_id,
        rates=rates.rates,
        composition=composition,
        composition_locations=np.array(list(locations)),
        population=population,
        population_years=np.asarray(population_years, dtype=np.int64),
    )
    path.with_suffix(".json").write_text(
        json.dumps(rates.provenance, indent=2) + "\n", encoding="utf-8"
    )
    return path


@dataclass(frozen=True)
class MigrationSource:
    """Everything needed to build the assumption, without re-reading the UN."""

    rates: MigrationRates
    composition: np.ndarray  # (L, 2, 101)
    locations: tuple[str, ...]
    population: np.ndarray  # (Y, L) on the UN medium path
    population_years: np.ndarray  # (Y,)


def load(path: Path | None = None) -> MigrationSource:
    path = path or bundle_path()
    if not path.exists():
        raise MigrationIngestError(
            f"{path.name} has not been built.\n"
            f"  Run:  python scripts/build_uw_migration.py --archive <mig1trajWPP2024.tgz>"
        )
    z = np.load(path, allow_pickle=False)
    provenance = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    return MigrationSource(
        rates=MigrationRates(
            years=z["years"], loc_id=z["loc_id"], rates=z["rates"], provenance=provenance
        ),
        composition=z["composition"],
        locations=tuple(str(c) for c in z["composition_locations"]),
        population=z["population"],
        population_years=z["population_years"],
    )

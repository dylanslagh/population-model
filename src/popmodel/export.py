"""Turn the model's arrays into files a browser can actually load.

Spec section 4.1: preprocess into per-country JSON at build time, do not ship
raw CSVs to the browser. The raw single-age files are a gigabyte; a population
pyramid is a few thousand numbers.

What each country file contains, and where it came from
-------------------------------------------------------
A pyramid every five years from 1950 to 2150, plus an annual total. Each year
is tagged with what kind of number it is, because they are not the same kind of
thing and a chart that blends them without saying so is misleading:

    estimate    1950-2023. The UN's reconstruction of what already happened.
                Still a model output rather than a measurement - see spec rule
                3 - but constrained by censuses and registration.
    projection  2024-2100. This project's engine, run on the UN's own fertility
                and mortality assumptions. Reproduces the UN medium variant.
    extension   2101-2150. The same engine past the end of published rates,
                holding fertility and mortality at their 2100 values. Nobody
                publishes this, which is the point, and it rests on an
                assumption the reader should be told about rather than a
                forecast anyone stands behind.

The tag travels with the data into the JSON so the map can draw the three
differently. A reader should be able to see where the evidence stops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from popmodel import paths
from popmodel.engine import cohort
from popmodel.ingest.wpp import (
    THOUSANDS_TO_PEOPLE,
    Bundle,
    _country_rows,
    _dense,
    _read,
    _require_complete,
)

HISTORY_START = 1950
HISTORY_END = 2023
BASE_YEAR = 2024  # where the UN's estimates stop and the projection starts
PYRAMID_STEP = 5
END_YEAR = 2150


def pyramid_years(start: int = HISTORY_START, end: int = END_YEAR, step: int = PYRAMID_STEP) -> np.ndarray:
    """Five-yearly, plus the two years either side of the seam.

    A plain five-year grid from 1950 skips 2024 entirely, which is the one year
    that must be there: it is where the UN's estimates stop and the projection
    starts, and it is what "now" means for the whole project. 2023 is included
    beside it so the last estimate and the first projected year can be compared
    directly rather than across a five-year gap.
    """
    grid = set(range(start, end + 1, step))
    grid.update({HISTORY_END, BASE_YEAR})
    return np.array(sorted(grid))


def year_kind(year: int) -> str:
    if year <= HISTORY_END:
        return "estimate"
    if year <= 2100:
        return "projection"
    return "extension"


@dataclass
class SiteData:
    """Everything the front end needs, before it is written to disk."""

    countries: pd.DataFrame
    years: np.ndarray  # pyramid years
    annual_years: np.ndarray
    female: np.ndarray  # (n_years, L, 101)
    male: np.ndarray
    annual_total: np.ndarray  # (n_annual, L)
    kinds: list[str]


def history(countries: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(years, (T, L, 2, 101)) the UN's estimates for 1950-2023, in people."""
    years = np.arange(HISTORY_START, HISTORY_END + 1)
    df = _read(
        "pop_jan1_single_hist",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "PopMale", "PopFemale"],
        lambda c: _country_rows(c, (HISTORY_START, HISTORY_END)),
    )
    dense = _dense(df, countries, years, ["PopFemale", "PopMale"], what="historical population")
    _require_complete(dense, "historical population", countries, years)
    return years, dense * THOUSANDS_TO_PEOPLE


def build(bundle: Bundle, countries: pd.DataFrame, run: cohort.ProjectionResult) -> SiteData:
    """Stitch estimates and projection into one series per country."""
    hist_years, hist = history(countries)

    years = pyramid_years()
    annual_years = np.arange(HISTORY_START, END_YEAR + 1)

    L = len(countries)
    female = np.zeros((len(years), L, cohort.N_AGES))
    male = np.zeros((len(years), L, cohort.N_AGES))
    annual = np.zeros((len(annual_years), L))

    hist_index = {int(y): i for i, y in enumerate(hist_years)}
    run_index = {int(y): i for i, y in enumerate(run.years)}
    run_totals = run.location_totals()

    for i, y in enumerate(years):
        y = int(y)
        if y in hist_index:
            block = hist[hist_index[y]]
        elif y in run_index:
            block = run.population[run_index[y]]
        else:
            raise KeyError(f"no source for pyramid year {y}")
        female[i] = block[:, cohort.FEMALE, :]
        male[i] = block[:, cohort.MALE, :]

    for i, y in enumerate(annual_years):
        y = int(y)
        if y in hist_index:
            annual[i] = hist[hist_index[y]].sum(axis=(1, 2))
        elif y in run_index:
            annual[i] = run_totals[run_index[y]]
        else:
            raise KeyError(f"no source for year {y}")

    return SiteData(
        countries=countries,
        years=years,
        annual_years=annual_years,
        female=female,
        male=male,
        annual_total=annual,
        kinds=[year_kind(int(y)) for y in years],
    )


def out_dir() -> Path:
    return paths.PROCESSED / "site"


def write(data: SiteData, crosswalk_table: pd.DataFrame) -> Path:
    """Write index.json plus one file per country."""
    root = out_dir()
    (root / "countries").mkdir(parents=True, exist_ok=True)

    cw = crosswalk_table.set_index("loc_id")
    index_rows = []

    for j, (_, c) in enumerate(data.countries.iterrows()):
        loc = int(c["LocID"])
        iso = c["ISO3_code"]
        totals = data.annual_total[:, j]
        peak = int(totals.argmax())

        payload = {
            "loc_id": loc,
            "iso3": iso,
            "name": c["Location"],
            "ages": list(range(cohort.N_AGES)),
            "years": [int(y) for y in data.years],
            "kinds": data.kinds,
            "female": [[int(round(v)) for v in row] for row in data.female[:, j, :]],
            "male": [[int(round(v)) for v in row] for row in data.male[:, j, :]],
            "annual_years": [int(data.annual_years[0]), int(data.annual_years[-1])],
            "annual_total": [int(round(v)) for v in totals],
        }
        (root / "countries" / f"{iso}.json").write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )

        index_rows.append({
            "loc_id": loc,
            "iso3": iso,
            "name": c["Location"],
            "has_shape": bool(cw.loc[loc, "has_shape"]) if loc in cw.index else False,
            "match": str(cw.loc[loc, "match"]) if loc in cw.index else "missing",
            "pop_2024": int(round(totals[int(2024 - HISTORY_START)])),
            "pop_2100": int(round(totals[int(2100 - HISTORY_START)])),
            "pop_2150": int(round(totals[-1])),
            "peak_year": int(data.annual_years[peak]),
            "peak_population": int(round(totals[peak])),
            "peaked_before_end": bool(peak < len(totals) - 1),
        })

    index = {
        "generated_from": "WPP 2024 estimates to 2023; this project's engine thereafter",
        "year_kinds": {
            "estimate": f"{HISTORY_START}-{HISTORY_END}, UN reconstruction of the past",
            "projection": "2024-2100, engine run on the UN's own assumptions",
            "extension": "2101-2150, same engine, rates held at their 2100 values",
        },
        "caveat": (
            "Migration makes country-level figures far less meaningful than world "
            "totals at long horizons. Spec section 12."
        ),
        "pyramid_years": [int(y) for y in data.years],
        "annual_years": [int(data.annual_years[0]), int(data.annual_years[-1])],
        "countries": index_rows,
    }
    (root / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    return root

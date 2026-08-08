"""The UN's own published answers, for checking ours against.

Kept in a separate module from wpp.py on purpose. Everything in wpp.py is an
INPUT to the engine. Everything here is a TARGET the engine is scored against.
Mixing the two is how a project ends up quietly testing a model on the numbers
it was handed, and then reporting the agreement as if it meant something.

Nothing in this module may be imported by the engine or by any scenario.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from popmodel.engine import cohort
from popmodel.ingest.wpp import IngestError, _country_rows, _dense, _read, THOUSANDS_TO_PEOPLE

# The variant names as WPP spells them.
MEDIUM = "Medium"
ZERO_MIGRATION = "Zero migration"
CONSTANT_FERTILITY = "Constant fertility"

# WPP's 1 January by-age files for the non-medium variants come in five-year
# groups: 0-4, 5-9, ..., 95-99, 100+.
AGE5_STARTS = np.array(list(range(0, 100, 5)) + [100])
N_AGE5 = len(AGE5_STARTS)


def variant_totals(countries: pd.DataFrame, years: np.ndarray, variant: str) -> np.ndarray:
    """(T, L) total population on 1 January under a named variant, in people."""
    key = "indicators_medium" if variant == MEDIUM else "indicators_variants"
    df = _read(
        key,
        ["LocID", "LocTypeName", "Time", "Variant", "TPopulation1Jan"],
        lambda c: _country_rows(c, (int(years[0]), int(years[-1])), variant=variant),
    )
    if df.empty:
        raise IngestError(f"no rows for variant {variant!r}")
    df = df.assign(AgeGrpStart=0)
    dense = _dense(df, countries, years, ["TPopulation1Jan"], n_ages=1, what=f"totals ({variant})")
    if np.isnan(dense).any():
        n = int(np.isnan(dense).sum())
        raise IngestError(f"totals ({variant}): {n} missing country-years")
    return dense[:, :, 0, 0] * THOUSANDS_TO_PEOPLE


def variant_age5(countries: pd.DataFrame, years: np.ndarray, variant: str) -> np.ndarray:
    """(T, L, 2, 21) population by five-year age group on 1 January, in people."""
    if variant == MEDIUM:
        raise ValueError("the medium variant's by-age file is the single-age one; use wpp.medium_population")
    df = _read(
        "pop_jan1_age5_variants",
        ["LocID", "LocTypeName", "Time", "Variant", "AgeGrpStart", "PopMale", "PopFemale"],
        lambda c: _country_rows(c, (int(years[0]), int(years[-1])), variant=variant),
    )
    if df.empty:
        raise IngestError(f"no by-age rows for variant {variant!r}")
    # Map 0,5,10,... -> 0,1,2,... so the dense pivot can use it as an index.
    df = df.assign(AgeIdx=(df["AgeGrpStart"] // 5).clip(upper=N_AGE5 - 1))
    dense = _dense(
        df,
        countries,
        years,
        ["PopFemale", "PopMale"],
        age_col="AgeIdx",
        n_ages=N_AGE5,
        what=f"by-age ({variant})",
    )
    if np.isnan(dense).any():
        n = int(np.isnan(dense).sum())
        raise IngestError(f"by-age ({variant}): {n} missing cells")
    return dense * THOUSANDS_TO_PEOPLE


def to_age5(pop: np.ndarray) -> np.ndarray:
    """Collapse single ages (..., 101) to WPP's five-year groups (..., 21)."""
    if pop.shape[-1] != cohort.N_AGES:
        raise ValueError(f"expected last axis {cohort.N_AGES}, got {pop.shape[-1]}")
    head = pop[..., :100].reshape(*pop.shape[:-1], 20, 5).sum(axis=-1)
    return np.concatenate([head, pop[..., 100:101]], axis=-1)

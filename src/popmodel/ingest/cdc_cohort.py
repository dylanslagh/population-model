"""Read the paired CDC/NCHS U.S. cohort-fertility tables.

Table 3 supplies the parity distribution and Table 2 supplies its exact mean.
Together they identify the mean of the open 7+ category, so the same explicit
tail models used for CFE can be applied to an independent national source.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from popmodel.ingest.cfe import CFEDataError, Distribution


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False), errors="coerce"
    )


def read_completed_distributions(
    distribution_path: Path,
    cumulative_rates_path: Path,
    *,
    cohort_from: int = 1947,
    cohort_to: int = 1956,
) -> list[Distribution]:
    """Return all-race U.S. cohorts observed at exact age 50."""
    parity = pd.read_csv(distribution_path, header=4)
    rates = pd.read_csv(cumulative_rates_path, header=4)
    parity.columns = [str(column).strip() for column in parity.columns]
    rates.columns = [str(column).strip() for column in rates.columns]

    keys = [
        "Race of women",
        "Year",
        "Exact age of women as of January 1 of year",
        "Cohort birth year of women",
    ]
    required_parity = set(keys) | {"Parity total"} | {
        f"Parity {level}" for level in range(7)
    } | {"Parity 7 and higher"}
    required_rates = set(keys) | {"Live-birth order total"}
    if missing := required_parity - set(parity):
        raise CFEDataError(f"CDC parity table is missing columns: {sorted(missing)}")
    if missing := required_rates - set(rates):
        raise CFEDataError(f"CDC rates table is missing columns: {sorted(missing)}")

    for frame in (parity, rates):
        for column in keys[1:]:
            frame[column] = _number(frame[column])
    parity = parity[
        (parity["Race of women"] == "All races1")
        & (parity[keys[2]] == 50)
        & parity[keys[3]].between(cohort_from, cohort_to)
    ].copy()
    rates = rates[
        (rates["Race of women"] == "All races1")
        & (rates[keys[2]] == 50)
        & rates[keys[3]].between(cohort_from, cohort_to)
    ].copy()
    merged = parity.merge(
        rates[keys + ["Live-birth order total"]],
        on=keys,
        how="inner",
        validate="one_to_one",
    )
    expected = cohort_to - cohort_from + 1
    if len(merged) != expected:
        raise CFEDataError(
            f"CDC tables yield {len(merged)} completed cohorts, expected {expected}"
        )

    output = []
    for _, row in merged.sort_values(keys[3]).iterrows():
        values = {
            level: float(_number(pd.Series([row[f"Parity {level}"]])).iloc[0])
            for level in range(7)
        }
        values[7] = float(
            _number(pd.Series([row["Parity 7 and higher"]])).iloc[0]
        )
        women = float(_number(pd.Series([row["Parity total"]])).iloc[0])
        children = float(
            _number(pd.Series([row["Live-birth order total"]])).iloc[0]
        )
        if abs(sum(values.values()) - women) > 0.5:
            raise CFEDataError("CDC parity proportions do not sum to their total")
        output.append(
            Distribution(
                country="United States",
                source="CDC/NCHS cohort fertility tables",
                observation_year=int(row["Year"]),
                cohort_from=int(row[keys[3]]),
                cohort_to=int(row[keys[3]]),
                women=women,
                children=children,
                parity=values,
                open_parity=7,
                unknown_parity=0.0,
            )
        )
    return output


"""Grade every past revision of World Population Prospects against what happened.

Spec phase 1, and spec section 9's claim that the scored track record is the
actual contribution. The UN has published fourteen revisions since 1992, each
one a set of projections, each quietly superseded by the next. Nobody goes back
and marks them.

What this measures, precisely
-----------------------------
For a vintage published in year V and a target year T that has since arrived,
compare the vintage's medium-variant projection for T against WPP 2024's
estimate for T. The horizon is T - V's base year: how far ahead it was looking.

Two honesty notes that belong in the output, not the footnotes:

1. **WPP 2024's estimates are not ground truth.** They are today's best
   reconstruction, produced by a model, and spec rule 3 forbids treating them
   as fact. At the world level the reconstruction is tight enough that the
   grades below are dominated by real forecast error. For a single weak-data
   country it may not be, which is why the headline results here are the world
   and continental aggregates rather than country league tables.

2. **The low and high variants are not a confidence interval.** They are
   fertility scenarios, roughly plus or minus half a child on the total
   fertility rate, with no probability attached. Coverage is still worth
   counting - it says whether reality stayed inside the range the UN was
   willing to print - but it is not calibration in the CRPS sense and is not
   reported as such.

Aggregates, not countries, on purpose
-------------------------------------
Country codes are stable across these files, but countries are not. The USSR,
Yugoslavia, Czechoslovakia, Sudan and Ethiopia all changed shape inside this
window, and a naive country join would silently drop or mismatch them. The UN's
region codes have no such problem: Africa was Africa in 1992 and is Africa now.
So the graded set is the world and the continental regions, which is also where
the interesting failures live.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from popmodel.ingest import archive
from popmodel.ingest.wpp import _read
from popmodel.sources import wpp_archive

# UN location codes that mean the same thing in 1992 and in 2024.
REPORT_LOCATIONS = {
    900: "World",
    903: "Africa",
    935: "Asia",
    908: "Europe",
    904: "Latin America and the Caribbean",
    905: "Northern America",
    909: "Oceania",
    906: "Eastern Asia",
}

# Which WPP 2024 column supplies the truth for each quantity, and how to scale
# it into the same units the archives use.
TRUTH_COLUMN = {
    "population": ("TPopulation1July", 1000.0),
    "tfr": ("TFR", 1.0),
    "life_expectancy": ("LEx", 1.0),
}

LAST_KNOWN_YEAR = 2024


@dataclass
class Grade:
    """One vintage's projection of one quantity, marked."""

    frame: pd.DataFrame  # vintage, loc_id, location, year, horizon, projected, actual, rel_error
    quantity: str


def truth(quantity: str, years: tuple[int, int]) -> pd.DataFrame:
    """WPP 2024's estimate, by location and year, for the graded locations."""
    column, scale = TRUTH_COLUMN[quantity]
    df = _read(
        "indicators_medium",
        ["LocID", "Time", "Variant", column],
        lambda c: (
            c["LocID"].isin(REPORT_LOCATIONS)
            & (c["Variant"] == "Medium")
            & (c["Time"] >= years[0])
            & (c["Time"] <= years[1])
        ),
    )
    out = df.rename(columns={"LocID": "loc_id", "Time": "year", column: "actual"})
    out["actual"] = out["actual"].astype(float) * scale
    return out[["loc_id", "year", "actual"]].dropna()


def _truth_for_periods(truth_annual: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Average the modern annual series over each archived five-year period.

    A 1994 projection of fertility for "2015-2020" is a period average. Lining
    it up against a single modern year would compare two different things.
    """
    rows = []
    for (loc, start, end), _ in periods.groupby(["loc_id", "period_start", "period_end"]):
        window = truth_annual[
            (truth_annual.loc_id == loc)
            & (truth_annual.year >= start)
            & (truth_annual.year < end)  # 2015-2020 means the five years 2015..2019
        ]
        if len(window) == 0:
            continue
        rows.append((loc, start, end, float(window["actual"].mean()), len(window)))
    return pd.DataFrame(rows, columns=["loc_id", "period_start", "period_end", "actual", "n_years"])


def grade(key: str, quantity: str) -> Grade:
    """Mark one vintage on one quantity."""
    rev = wpp_archive.REVISIONS[key]
    series = archive.load_series(key, quantity, "medium")
    df = series.frame[series.frame.loc_id.isin(REPORT_LOCATIONS)].copy()

    # Only grade years that have actually happened, and only projections -
    # a vintage's own estimates of its own past are not forecasts.
    df = df[(df.period_start > rev.base_year) & (df.period_end <= LAST_KNOWN_YEAR)]
    if df.empty:
        return Grade(frame=pd.DataFrame(), quantity=quantity)

    annual = truth(quantity, (int(df.period_start.min()), LAST_KNOWN_YEAR))

    if series.is_period:
        matched = _truth_for_periods(annual, df)
        df = df.merge(matched, on=["loc_id", "period_start", "period_end"], how="inner")
    else:
        df = df.merge(
            annual.rename(columns={"year": "period_start"}), on=["loc_id", "period_start"], how="inner"
        )

    if df.empty:
        return Grade(frame=pd.DataFrame(), quantity=quantity)

    df["vintage"] = rev.year
    df["location"] = df.loc_id.map(REPORT_LOCATIONS)
    df["horizon"] = df.period_start - rev.base_year
    df["projected"] = df["value"]
    df["rel_error"] = df.projected / df.actual - 1.0
    df["abs_error"] = df.projected - df.actual

    cols = ["vintage", "loc_id", "location", "year", "period_start", "period_end",
            "horizon", "projected", "actual", "abs_error", "rel_error"]
    return Grade(frame=df[cols].sort_values(["loc_id", "year"]).reset_index(drop=True), quantity=quantity)


def grade_all(quantity: str, keys: list[str] | None = None) -> pd.DataFrame:
    keys = keys or wpp_archive.DEFAULT_KEYS
    frames = [grade(k, quantity).frame for k in keys]
    frames = [f for f in frames if len(f)]
    if not frames:
        raise RuntimeError(f"no gradeable {quantity} data in {keys}")
    return pd.concat(frames, ignore_index=True)


def interval_coverage(key: str) -> pd.DataFrame:
    """Did the world's actual population stay inside the low-high band?

    Not a calibration statistic - the variants carry no probability - but a
    direct answer to "was reality inside the range the UN was willing to print".
    """
    rev = wpp_archive.REVISIONS[key]
    low = archive.load_series(key, "population", "low").frame
    high = archive.load_series(key, "population", "high").frame
    med = archive.load_series(key, "population", "medium").frame
    band = (
        med.rename(columns={"value": "medium"})
        .merge(low.rename(columns={"value": "low"})[["loc_id", "period_start", "low"]],
               on=["loc_id", "period_start"])
        .merge(high.rename(columns={"value": "high"})[["loc_id", "period_start", "high"]],
               on=["loc_id", "period_start"])
    )
    band = band[band.loc_id.isin(REPORT_LOCATIONS)]
    band = band[(band.period_start > rev.base_year) & (band.period_start <= LAST_KNOWN_YEAR)]
    if band.empty:
        return pd.DataFrame()
    annual = truth("population", (int(band.period_start.min()), LAST_KNOWN_YEAR))
    band = band.merge(annual.rename(columns={"year": "period_start"}), on=["loc_id", "period_start"])
    band["vintage"] = rev.year
    band["location"] = band.loc_id.map(REPORT_LOCATIONS)
    band["horizon"] = band.period_start - rev.base_year
    band["inside"] = (band.actual >= band.low) & (band.actual <= band.high)
    return band[["vintage", "loc_id", "location", "period_start", "horizon",
                 "low", "medium", "high", "actual", "inside"]]


def by_horizon(graded: pd.DataFrame, loc_id: int = 900) -> pd.DataFrame:
    """Mean signed and absolute error against how far ahead the forecast looked."""
    w = graded[graded.loc_id == loc_id].copy()
    w["bucket"] = pd.cut(
        w.horizon,
        bins=[0, 10, 20, 30, 40, 100],
        labels=["1-10 yr", "11-20 yr", "21-30 yr", "31-40 yr", "40+ yr"],
        right=True,
    )
    g = w.groupby("bucket", observed=True).agg(
        n=("rel_error", "size"),
        mean_signed=("rel_error", "mean"),
        mean_absolute=("rel_error", lambda s: np.abs(s).mean()),
        worst=("rel_error", lambda s: s.iloc[np.abs(s).argmax()]),
    )
    return g.reset_index()

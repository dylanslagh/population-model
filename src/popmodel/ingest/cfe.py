"""Read CFE cohort-parity tables and estimate completed-family-size spread.

The observable is the distribution of children ever born to women in a real
birth cohort.  It includes childless women.  The highest parity is open-ended
(usually 8+), but CFE also gives the exact total number of children, so the
tail mean is known.  Its within-tail variance is not; :func:`moments` exposes
three transparent treatments rather than silently pretending 8+ means eight.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from functools import reduce
from pathlib import Path

import pandas as pd

from popmodel.sources.cfe import Dataset


class CFEDataError(RuntimeError):
    """A source table is incomplete or internally inconsistent."""


# The CFE methods protocol says these censuses treat unknown parity as
# childlessness rather than dropping it.  The country-specific documentation
# is authoritative for this exception.
UNKNOWN_AS_CHILDLESS = {"Czech Republic", "Slovakia"}


def _reporting_increment(values: pd.Series) -> float:
    """Infer the smallest published count unit (for example 0.01 or 1,000)."""
    decimals = [Decimal(str(value)) for value in values.dropna() if float(value) != 0]
    if not decimals:
        return 0.0
    places = max(max(0, -value.as_tuple().exponent) for value in decimals)
    scale = 10**places
    integers = [abs(int(value * scale)) for value in decimals]
    return reduce(math.gcd, integers) / scale


@dataclass(frozen=True)
class Distribution:
    country: str
    source: str
    observation_year: int | None
    cohort_from: int
    cohort_to: int
    women: float
    children: float
    parity: dict[int, float]
    open_parity: int
    unknown_parity: float


@dataclass(frozen=True)
class Moments:
    mean: float
    variance: float
    cv: float
    open_share: float
    open_mean: float | None
    tail_model: str


def _select_origin_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Use an origin total if supplied, otherwise sum exclusive categories."""
    kept = []
    group_cols = [
        "cohort_from",
        "cohort_to",
        "edu_eurrep",
        "edu_from",
        "edu_to",
        "sex",
        "stat",
    ]
    for _, group in frame.groupby(group_cols, dropna=False, sort=False):
        total = group[group["origin"].astype(str).str.casefold() == "total"]
        kept.append(total if not total.empty else group)
    return pd.concat(kept, ignore_index=True)


def read_distributions(
    path: Path,
    dataset: Dataset,
    *,
    minimum_cohort: int | None = None,
    maximum_cohort: int | None = None,
) -> list[Distribution]:
    frame = pd.read_csv(path)
    required = {
        "country",
        "data_source",
        "cohort_from",
        "cohort_to",
        "edu_eurrep",
        "edu_from",
        "edu_to",
        "sex",
        "origin",
        "stat",
        "value",
    }
    missing = required - set(frame.columns)
    if missing:
        raise CFEDataError(f"{path.name} is missing columns: {sorted(missing)}")

    countries = set(frame["country"].dropna().astype(str))
    sources = set(frame["data_source"].dropna().astype(str))
    if countries != {dataset.country} or sources != {dataset.source}:
        raise CFEDataError(
            f"{path.name} identifies {countries} / {sources}, expected "
            f"{dataset.country!r} / {dataset.source!r}"
        )

    frame = frame[frame["sex"].astype(str).str.upper() == "F"].copy()
    frame = frame[(frame["cohort_from"] >= 0) & (frame["cohort_to"] >= 0)]
    numeric_parity_mask = frame["stat"].astype(str).str.match(r"^parity_\d+$")
    count_increment = _reporting_increment(
        frame.loc[
            numeric_parity_mask
            | frame["stat"].isin(["women_total", "parity_unknown"]),
            "value",
        ]
    )
    child_increment = _reporting_increment(
        frame.loc[frame["stat"] == "children_total", "value"]
    )
    parity_levels = [
        int(name.removeprefix("parity_"))
        for name in frame["stat"].dropna().astype(str).unique()
        if name.startswith("parity_")
        and name.removeprefix("parity_").isdigit()
    ]
    if not parity_levels:
        raise CFEDataError(f"{dataset.key} contains no numeric parity categories")
    # The archive omits zero cells.  Consequently the largest parity present
    # in one cohort is not necessarily the dataset's documented open category.
    dataset_open_parity = max(parity_levels)
    if minimum_cohort is not None:
        frame = frame[frame["cohort_from"] >= minimum_cohort]
    if maximum_cohort is not None:
        frame = frame[frame["cohort_to"] <= maximum_cohort]
    if frame.empty:
        return []
    frame = _select_origin_rows(frame)

    distributions: list[Distribution] = []
    for (cohort_from, cohort_to), group in frame.groupby(
        ["cohort_from", "cohort_to"], sort=True
    ):
        stats = group.groupby("stat", sort=False)["value"].sum()
        reported_parity = {
            int(name.removeprefix("parity_")): float(value)
            for name, value in stats.items()
            if str(name).startswith("parity_")
            and str(name).removeprefix("parity_").isdigit()
        }
        if not reported_parity and dataset.country not in UNKNOWN_AS_CHILDLESS:
            raise CFEDataError(
                f"{dataset.key} cohort {cohort_from}-{cohort_to} has no parity counts"
            )
        open_parity = dataset_open_parity
        parity_keys = {
            level: reported_parity.get(level, 0.0)
            for level in range(open_parity + 1)
        }
        unknown = float(stats.get("parity_unknown", 0.0))
        women_total = float(stats.get("women_total", math.nan))
        children = float(stats.get("children_total", math.nan))
        if not math.isfinite(women_total):
            raise CFEDataError(
                f"{dataset.key} cohort {cohort_from}-{cohort_to} lacks women_total"
            )
        # The database uses sparse rows: children_total is absent when it is
        # exactly zero.  A missing value can only survive the minimum-children
        # consistency check below when every reported woman is childless.
        if not math.isfinite(children):
            children = 0.0

        parity = dict(parity_keys)
        if dataset.country in UNKNOWN_AS_CHILDLESS:
            parity[0] = parity.get(0, 0.0) + unknown
            women = women_total
        else:
            women = women_total - unknown

        counted = sum(parity.values())
        group_stats = group["stat"].astype(str)
        count_cells = group[
            group_stats.str.match(r"^parity_\d+$")
            | group_stats.isin(["women_total", "parity_unknown"])
        ]
        count_rounding_tolerance = max(
            1e-6,
            1e-8 * women,
            0.5 * count_increment * len(count_cells),
        )
        if abs(counted - women) > count_rounding_tolerance:
            raise CFEDataError(
                f"{dataset.key} cohort {cohort_from}-{cohort_to}: parity counts "
                f"sum to {counted:g}, but adjusted women total is {women:g}"
            )
        # Use the parity sum as the analysis denominator when weighted source
        # cells differ from their separately rounded total by a fraction of a
        # woman.  This preserves a probability distribution summing to one.
        women = counted
        minimum_children = sum(k * n for k, n in parity.items())
        child_cells = group[group_stats == "children_total"]
        parity_rounding_weight = sum(
            int(stat.removeprefix("parity_"))
            for stat in group_stats
            if stat.startswith("parity_")
            and stat.removeprefix("parity_").isdigit()
        )
        child_rounding_tolerance = max(
            1e-6,
            1e-8 * max(children, minimum_children),
            0.5 * child_increment * len(child_cells)
            + 0.5 * count_increment * parity_rounding_weight,
        )
        if children + child_rounding_tolerance < minimum_children:
            raise CFEDataError(
                f"{dataset.key} cohort {cohort_from}-{cohort_to}: exact child "
                "total is below the parity-table minimum"
            )
        if parity[open_parity] == 0 and abs(children - minimum_children) <= (
            child_rounding_tolerance
        ):
            # With no women in the open category, every parity is exact and a
            # small residual can only be separate rounding of children_total.
            children = minimum_children
        else:
            children = max(children, minimum_children)
        distributions.append(
            Distribution(
                country=dataset.country,
                source=dataset.source,
                observation_year=dataset.observation_year,
                cohort_from=int(cohort_from),
                cohort_to=int(cohort_to),
                women=women,
                children=children,
                parity=parity,
                open_parity=open_parity,
                unknown_parity=unknown,
            )
        )
    return distributions


def combine(distributions: list[Distribution]) -> Distribution:
    if not distributions:
        raise CFEDataError("cannot combine an empty set of cohort distributions")
    first = distributions[0]
    for d in distributions[1:]:
        if (d.country, d.source, d.open_parity) != (
            first.country,
            first.source,
            first.open_parity,
        ):
            raise CFEDataError("combined cohorts must share country, source, and top code")
    parity = {
        k: sum(d.parity.get(k, 0.0) for d in distributions)
        for k in range(first.open_parity + 1)
    }
    return Distribution(
        country=first.country,
        source=first.source,
        observation_year=first.observation_year,
        cohort_from=min(d.cohort_from for d in distributions),
        cohort_to=max(d.cohort_to for d in distributions),
        women=sum(d.women for d in distributions),
        children=sum(d.children for d in distributions),
        parity=parity,
        open_parity=first.open_parity,
        unknown_parity=sum(d.unknown_parity for d in distributions),
    )


def moments(
    distribution: Distribution,
    *,
    tail_model: str = "geometric",
    tail_cap: int = 20,
) -> Moments:
    """Compute moments with an explicit model for the open parity category.

    ``minimum`` gives the smallest integer-valued tail variance compatible
    with the known tail mean. ``geometric`` uses the maximum-entropy geometric
    distribution for excess children above the top code. ``bounded-maximum``
    gives the largest variance compatible with the known mean and ``tail_cap``.
    """
    d = distribution
    if d.women <= 0 or d.children <= 0:
        raise CFEDataError("a fertility distribution needs positive women and children")
    m = d.open_parity
    n_tail = d.parity[m]
    fixed_children = sum(k * n for k, n in d.parity.items() if k < m)
    fixed_second = sum(k * k * n for k, n in d.parity.items() if k < m)
    tail_children = d.children - fixed_children
    tail_mean = tail_children / n_tail if n_tail else None
    if n_tail == 0:
        if abs(tail_children) > 1e-6:
            raise CFEDataError("nonzero tail children with no women in the open parity")
        tail_second = 0.0
    else:
        if tail_mean is None or tail_mean + 1e-8 < m:
            raise CFEDataError(
                f"open parity {m}+ has an impossible mean of {tail_mean}"
            )
        tail_mean = max(float(m), tail_mean)
        if tail_model == "minimum":
            lo = math.floor(tail_mean)
            hi = math.ceil(tail_mean)
            if lo == hi:
                second = tail_mean * tail_mean
            else:
                high_share = tail_mean - lo
                second = (1.0 - high_share) * lo * lo + high_share * hi * hi
        elif tail_model == "geometric":
            excess = tail_mean - m
            second = tail_mean * tail_mean + excess * (1.0 + excess)
        elif tail_model == "bounded-maximum":
            if tail_mean > tail_cap + 1e-8:
                raise CFEDataError(
                    f"tail cap {tail_cap} is below the observed tail mean {tail_mean:.2f}"
                )
            tail_mean = min(float(tail_cap), tail_mean)
            variance = (tail_mean - m) * (tail_cap - tail_mean)
            second = tail_mean * tail_mean + variance
        else:
            raise ValueError(f"unknown tail model: {tail_model}")
        tail_second = n_tail * second

    mean = d.children / d.women
    variance = (fixed_second + tail_second) / d.women - mean * mean
    if variance < -1e-9:
        raise CFEDataError(f"computed a negative variance: {variance}")
    variance = max(0.0, variance)
    return Moments(
        mean=mean,
        variance=variance,
        cv=math.sqrt(variance) / mean,
        open_share=n_tail / d.women,
        open_mean=tail_mean,
        tail_model=tail_model,
    )


def completed_age_window(
    distributions: list[Distribution],
    *,
    minimum_age: int = 50,
    maximum_age: int = 59,
) -> Distribution | None:
    """Pool whole cohort bins whose youngest and oldest are inside an age window."""
    if not distributions or distributions[0].observation_year is None:
        return None
    year = distributions[0].observation_year
    selected = [
        d
        for d in distributions
        if year - d.cohort_to >= minimum_age
        and year - d.cohort_from <= maximum_age
    ]
    return combine(selected) if selected else None

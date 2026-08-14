"""Measure completed-family-size dispersion in the pinned CFE datasets.

The primary comparison uses women aged 50-59 at each census/register: old
enough to have completed childbearing, but not so old that differential
mortality has had decades to reshape the observed parity distribution.  Whole
cohort bins are retained; a five-year bin is never split fractionally.

Outputs contain derived moments only, never the source cell counts that the CFE
terms ask users not to redistribute.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths
from popmodel.ingest.cdc_cohort import read_completed_distributions
from popmodel.ingest.cfe import (
    UNKNOWN_AS_CHILDLESS,
    combine,
    completed_age_window,
    moments,
    read_distributions,
)
from popmodel.sources import cfe
from popmodel.sources import cdc_cohort


RAW = paths.RAW / "CFE"
OUT_JSON = paths.REFERENCE / "mainstream_propensity_cv.json"
OUT_CSV = paths.REFERENCE / "mainstream_propensity_cv.csv"
OUT_FIGURE = paths.REPO_ROOT / "docs" / "mainstream-propensity-cv.svg"
OUT_PNG = paths.OUT / "mainstream-propensity-cv.png"
CDC_RAW = paths.RAW / "CDC"


def weighted_quantile(values: list[float], weights: list[float], q: float) -> float:
    pairs = sorted(zip(values, weights, strict=True))
    target = q * sum(weights)
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return value
    return pairs[-1][0]


def summarize(rows: list[dict]) -> dict:
    cvs = [row["cv_geometric"] for row in rows]
    weights = [row["women"] for row in rows]
    quantiles = statistics.quantiles(cvs, n=10, method="inclusive")
    return {
        "countries": len(rows),
        "women": int(sum(weights)),
        "unweighted_median": statistics.median(cvs),
        "unweighted_min": min(cvs),
        "unweighted_max": max(cvs),
        "unweighted_p10": quantiles[0],
        "unweighted_p90": quantiles[8],
        "women_weighted_median": weighted_quantile(cvs, weights, 0.5),
        "women_weighted_p10": weighted_quantile(cvs, weights, 0.1),
        "women_weighted_p90": weighted_quantile(cvs, weights, 0.9),
    }


def main() -> None:
    rows = []
    excluded = []
    tail_differences = []
    for key, dataset in cfe.DATASETS.items():
        if dataset.observation_year is None:
            excluded.append(
                {
                    "key": key,
                    "country": dataset.country,
                    "reason": "pooled surveys have no single observation year",
                }
            )
            continue
        path = RAW / dataset.filename
        if not path.exists():
            raise FileNotFoundError(
                f"{path} is missing; run python scripts/fetch_cfe.py first"
            )
        distributions = read_distributions(
            path,
            dataset,
            minimum_cohort=dataset.observation_year - 59,
            maximum_cohort=dataset.observation_year - 50,
        )
        pooled = completed_age_window(distributions, minimum_age=50, maximum_age=59)
        if pooled is None:
            excluded.append(
                {
                    "key": key,
                    "country": dataset.country,
                    "reason": "no whole cohort bin entirely inside ages 50-59",
                }
            )
            continue
        minimum = moments(pooled, tail_model="minimum")
        geometric = moments(pooled, tail_model="geometric")
        bounded = moments(pooled, tail_model="bounded-maximum", tail_cap=40)
        row = {
            "key": key,
            "country": dataset.country,
            "data_source": dataset.source,
            "observation_year": dataset.observation_year,
            "cohort_from": pooled.cohort_from,
            "cohort_to": pooled.cohort_to,
            "women": int(pooled.women),
            "mean_children": geometric.mean,
            "variance_geometric": geometric.variance,
            "cv_minimum_tail": minimum.cv,
            "cv_geometric": geometric.cv,
            "cv_bounded_max_tail": bounded.cv,
            "open_parity": pooled.open_parity,
            "open_share": geometric.open_share,
            "open_mean": geometric.open_mean,
            "unknown_share_reported": pooled.unknown_parity
            / (
                pooled.women
                if pooled.country in UNKNOWN_AS_CHILDLESS
                else pooled.women + pooled.unknown_parity
            ),
            "poisson_cv": 1.0 / math.sqrt(geometric.mean),
            "excess_variance": geometric.variance - geometric.mean,
        }
        rows.append(row)
        tail_differences.append(bounded.cv - minimum.cv)

    if len(rows) < 30:
        raise RuntimeError(f"only {len(rows)} usable countries; expected broad coverage")

    # A low-fertility subset matches the settings where the mechanistic layer is
    # intended to describe the general population.  The threshold is declared,
    # not fitted to the model result.
    low_fertility = [row for row in rows if row["mean_children"] <= 2.2]
    overall = summarize(rows)
    low_summary = summarize(low_fertility)

    cdc_cohorts = read_completed_distributions(
        CDC_RAW / "Table03.csv", CDC_RAW / "Table02.csv"
    )
    cdc_pooled = combine(cdc_cohorts)
    cdc_minimum = moments(cdc_pooled, tail_model="minimum")
    cdc_geometric = moments(cdc_pooled, tail_model="geometric")
    cdc_bounded = moments(
        cdc_pooled, tail_model="bounded-maximum", tail_cap=40
    )

    selected = {"value": 0.57, "low": 0.44, "high": 0.80}
    if not (
        abs(low_summary["unweighted_median"] - selected["value"]) < 0.01
        and selected["low"] <= low_summary["unweighted_min"]
        and selected["high"] >= low_summary["unweighted_max"]
    ):
        raise RuntimeError(
            "declared parameter no longer summarizes the pinned low-fertility data"
        )

    # The observed CV contains counting/process noise as well as persistent
    # differences.  A Poisson variance subtraction is only a diagnostic lower
    # decomposition, not the chosen parameter: low-fertility distributions are
    # often underdispersed, and completed family size is not literally Poisson.
    for row in rows:
        row["excess_cv_if_poisson"] = (
            math.sqrt(max(0.0, row["excess_variance"])) / row["mean_children"]
        )

    result = {
        "generated": cfe.ACCESSED,
        "source": "Cohort Fertility and Education Database",
        "source_page": cfe.SOURCE_PAGE,
        "methods": cfe.METHODS,
        "terms": cfe.TERMS,
        "unit": "women; children ever born, including childless women",
        "primary_window": (
            "whole birth-cohort bins whose members were all aged 50-59 at "
            "the source observation year"
        ),
        "tail_models": {
            "minimum": (
                "smallest integer-valued variance consistent with the exact mean "
                "of the open highest-parity category"
            ),
            "geometric": (
                "geometric excess above the open parity, preserving its exact mean; "
                "used for the primary CV"
            ),
            "bounded-maximum": (
                "largest variance on the open-parity to 40-child interval that is "
                "consistent with its exact mean"
            ),
        },
        "all_usable": overall,
        "low_fertility_mean_le_2_2": low_summary,
        "us_cross_check": {
            "source": "CDC/NCHS Cohort Fertility Tables 2 and 3",
            "source_page": cdc_cohort.SOURCE_PAGE,
            "technical_appendix": cdc_cohort.TECHNICAL_APPENDIX,
            "cohorts": [cdc_pooled.cohort_from, cdc_pooled.cohort_to],
            "age": 50,
            "mean_children": cdc_geometric.mean,
            "cv_minimum_tail": cdc_minimum.cv,
            "cv_geometric": cdc_geometric.cv,
            "cv_bounded_max_tail": cdc_bounded.cv,
        },
        "open_tail_sensitivity": {
            "geometric_minus_minimum_median": statistics.median(
                row["cv_geometric"] - row["cv_minimum_tail"] for row in rows
            ),
            "geometric_minus_minimum_maximum": max(
                row["cv_geometric"] - row["cv_minimum_tail"] for row in rows
            ),
            "bounded_40_minus_minimum_median": statistics.median(tail_differences),
            "bounded_40_minus_minimum_maximum": max(tail_differences),
        },
        "recommended_parameter": {
            **selected,
            "selection_rule": (
                "value is the low-fertility country median rounded to two decimals; "
                "range rounds outward from the observed country minimum and maximum"
            ),
            "definition": (
                "effective CV of realized completed family size, paired with the "
                "observed intergenerational correlation to moment-match the "
                "parent-offspring fertility covariance"
            ),
        },
        "excluded": excluded,
        "rows": rows,
        "interpretation": {
            "observed": (
                "The total completed-family-size CV in contemporary low-fertility "
                "cohorts. It includes persistent between-person differences and "
                "nonpersistent process, partnership, infertility, and measurement variation."
            ),
            "not_identified": (
                "A latent fertility-propensity CV cannot be identified from parity "
                "marginals alone. Parent-child correlations identify persistence of "
                "observed family size but do not partition its variance into a stable trait."
            ),
            "why_total_cv_is_used": (
                "Fertility-weighting changes the next generation's mean by "
                "Cov(parent completed fertility, offspring completed fertility) / "
                "mean parent fertility. With equal marginal variance this is exactly "
                "correlation * CV^2 in relative terms, the one-generation response "
                "generated by this model's CV-and-persistence pair. This is moment "
                "matching, not a claim that all observed variance is a latent trait."
            ),
            "poisson_warning": (
                "A Poisson variance subtraction is not used: most model-relevant "
                "low-fertility countries here are underdispersed relative to Poisson, "
                "consistent with parity-targeting rather than a simple rate process."
            ),
        },
    }

    OUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    import matplotlib.pyplot as plt

    us_plot = {
        "country": "United States (CDC check)",
        "mean_children": cdc_geometric.mean,
        "cv_minimum_tail": cdc_minimum.cv,
        "cv_geometric": cdc_geometric.cv,
        "cv_bounded_max_tail": cdc_bounded.cv,
    }
    plot_rows = sorted(rows + [us_plot], key=lambda row: row["cv_geometric"])
    figure, axis = plt.subplots(figsize=(10, 10))
    y = list(range(len(plot_rows)))
    axis.hlines(
        y,
        [row["cv_minimum_tail"] for row in plot_rows],
        [row["cv_bounded_max_tail"] for row in plot_rows],
        color="#b7c5ca",
        linewidth=3,
        label="Open-tail bounds",
    )
    low_indices = [
        index
        for index, row in enumerate(plot_rows)
        if row["mean_children"] <= 2.2 and row["country"] != us_plot["country"]
    ]
    other_indices = [
        index
        for index, row in enumerate(plot_rows)
        if row["mean_children"] > 2.2
    ]
    us_index = next(
        index for index, row in enumerate(plot_rows) if row["country"] == us_plot["country"]
    )
    axis.scatter(
        [plot_rows[index]["cv_geometric"] for index in low_indices],
        low_indices,
        color="#176b73",
        s=28,
        zorder=3,
        label="Low fertility (mean <= 2.2)",
    )
    axis.scatter(
        [plot_rows[index]["cv_geometric"] for index in other_indices],
        other_indices,
        facecolors="white",
        edgecolors="#60777f",
        s=26,
        zorder=3,
        label="Other CFE countries",
    )
    axis.scatter(
        [us_plot["cv_geometric"]],
        [us_index],
        marker="D",
        color="#d18b32",
        s=34,
        zorder=4,
        label="U.S. CDC check",
    )
    axis.axvline(0.60, color="#b24b3e", linestyle="--", label="Old assumed value (0.60)")
    axis.axvline(
        selected["value"],
        color="#153f52",
        linewidth=2,
        label="Selected low-fertility country median (0.57)",
    )
    axis.set_yticks(y, [row["country"] for row in plot_rows], fontsize=8)
    axis.set_xlabel("CV of completed number of children")
    axis.set_title("Completed-family-size dispersion, women aged 50-59")
    axis.grid(axis="x", alpha=0.2)
    axis.legend(loc="lower right", fontsize=8)
    figure.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUT_PNG, dpi=160)
    figure.savefig(OUT_FIGURE)
    plt.close(figure)

    print(f"usable countries: {len(rows)}; excluded: {len(excluded)}")
    print(
        "all-country median CV: "
        f"{overall['unweighted_median']:.3f}; weighted median "
        f"{overall['women_weighted_median']:.3f}"
    )
    print(
        "low-fertility (mean <= 2.2) countries: "
        f"{low_summary['countries']}; median {low_summary['unweighted_median']:.3f}; "
        f"weighted median {low_summary['women_weighted_median']:.3f}; "
        f"weighted p10-p90 {low_summary['women_weighted_p10']:.3f}-"
        f"{low_summary['women_weighted_p90']:.3f}"
    )
    print(
        "U.S. CDC cohorts 1947-1956: mean "
        f"{cdc_geometric.mean:.3f}; CV {cdc_geometric.cv:.3f}"
    )
    print(f"wrote {OUT_JSON}, {OUT_CSV}, and {OUT_FIGURE}")


if __name__ == "__main__":
    main()

from pathlib import Path

import pytest

from popmodel.ingest.cdc_cohort import read_completed_distributions
from popmodel.ingest.cfe import moments


def _table(path: Path, header: str, row: str) -> None:
    padding = "," * header.count(",")
    path.write_text(
        "title"
        + padding
        + "\n"
        + padding
        + "\nnotes"
        + padding
        + "\n"
        + padding
        + "\n"
        + header
        + "\n"
        + row
        + "\n",
        encoding="utf-8",
    )


def test_cdc_tables_pair_parity_distribution_with_exact_mean(tmp_path: Path) -> None:
    parity = tmp_path / "Table03.csv"
    rates = tmp_path / "Table02.csv"
    keys = (
        "Race of women,Year,Exact age of women as of January 1 of year,"
        "Cohort birth year of women"
    )
    _table(
        parity,
        keys
        + ",Parity total,Parity 0,Parity 1,Parity 2,Parity 3,Parity 4,"
        "Parity 5,Parity 6,Parity 7 and higher",
        "All races1,2006,50,1956,1000,160,180,350,195,72,25,10,8",
    )
    _table(
        rates,
        keys + ",Live-birth order total",
        'All races1,2006,50,1956,"2,040.0"',
    )
    distributions = read_completed_distributions(
        parity, rates, cohort_from=1956, cohort_to=1956
    )
    assert len(distributions) == 1
    estimate = moments(distributions[0])
    assert estimate.mean == pytest.approx(2.04)
    assert estimate.open_mean is not None and estimate.open_mean >= 7

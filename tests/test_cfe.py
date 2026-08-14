from pathlib import Path

import pytest

from popmodel.ingest.cfe import (
    CFEDataError,
    Distribution,
    completed_age_window,
    moments,
    read_distributions,
)
from popmodel.sources.cfe import Dataset


def test_open_tail_models_preserve_the_exact_mean() -> None:
    distribution = Distribution(
        country="Example",
        source="Census 2000",
        observation_year=2000,
        cohort_from=1940,
        cohort_to=1940,
        women=100,
        children=220,
        parity={0: 10, 1: 15, 2: 45, 3: 20, 4: 5, 5: 5},
        open_parity=5,
        unknown_parity=0,
    )
    estimates = [
        moments(distribution, tail_model="minimum"),
        moments(distribution, tail_model="geometric"),
        moments(distribution, tail_model="bounded-maximum", tail_cap=20),
    ]
    assert all(m.mean == pytest.approx(2.2) for m in estimates)
    assert estimates[0].variance < estimates[1].variance < estimates[2].variance
    assert estimates[0].open_mean == pytest.approx(7.0)


def test_reader_excludes_unknown_parity_and_uses_exact_tail_total(tmp_path: Path) -> None:
    path = tmp_path / "example.csv"
    path.write_text(
        "country,data_source,cohort_from,cohort_to,edu_eurrep,edu_from,edu_to,sex,origin,stat,value\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,women_total,11\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,children_total,19\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_0,2\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_1,2\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_2,5\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_3,1\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_unknown,1\n",
        encoding="utf-8",
    )
    dataset = Dataset("example", "Example", "Census 2000", 2000)
    distribution = read_distributions(path, dataset)[0]
    assert distribution.women == 10
    assert distribution.children == 19
    assert moments(distribution).mean == pytest.approx(1.9)
    assert moments(distribution).open_mean == pytest.approx(7.0)


def test_reader_rejects_incomplete_parity_counts(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "country,data_source,cohort_from,cohort_to,edu_eurrep,edu_from,edu_to,sex,origin,stat,value\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,women_total,10\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,children_total,10\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_0,2\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_1,5\n",
        encoding="utf-8",
    )
    dataset = Dataset("example", "Example", "Census 2000", 2000)
    with pytest.raises(CFEDataError, match="sum to"):
        read_distributions(path, dataset)


def test_reader_uses_dataset_open_parity_and_allows_weight_rounding(
    tmp_path: Path,
) -> None:
    path = tmp_path / "weighted.csv"
    path.write_text(
        "country,data_source,cohort_from,cohort_to,edu_eurrep,edu_from,edu_to,sex,origin,stat,value\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,women_total,33.05\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,children_total,231.32\n"
        "Example,Census 2000,1940,1940,Level 1,A,B,F,Total,parity_7,33.05\n"
        "Example,Census 2000,1941,1941,Level 1,A,B,F,Total,women_total,1\n"
        "Example,Census 2000,1941,1941,Level 1,A,B,F,Total,children_total,8\n"
        "Example,Census 2000,1941,1941,Level 1,A,B,F,Total,parity_8,1\n",
        encoding="utf-8",
    )
    dataset = Dataset("example", "Example", "Census 2000", 2000)
    distributions = read_distributions(path, dataset)
    first = distributions[0]
    assert first.open_parity == 8
    assert first.parity[8] == 0
    assert first.children == pytest.approx(7 * 33.05)


def test_completed_age_window_keeps_only_whole_bins() -> None:
    base = dict(
        country="Example",
        source="Census 2000",
        observation_year=2000,
        women=10,
        children=20,
        parity={0: 1, 1: 2, 2: 4, 3: 2, 4: 1},
        open_parity=4,
        unknown_parity=0,
    )
    distributions = [
        Distribution(cohort_from=1940, cohort_to=1944, **base),
        Distribution(cohort_from=1945, cohort_to=1949, **base),
        Distribution(cohort_from=1950, cohort_to=1954, **base),
    ]
    pooled = completed_age_window(distributions, minimum_age=50, maximum_age=59)
    assert pooled is not None
    assert (pooled.cohort_from, pooled.cohort_to) == (1945, 1949)
    assert pooled.women == 10

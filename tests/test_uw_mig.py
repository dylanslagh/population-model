"""Tests for the migration source and the three decisions inside it.

The rate-to-count arithmetic and the borrowed age composition are the parts
that produce a plausible wrong answer rather than an error, so they are what
these check.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from popmodel.bayes import SeriesExtension
from popmodel.engine import cohort
from popmodel.ingest import uw_mig


def write_csv(path, *, locations=2, years=(2023, 2024), trajectories=2, value=0.01):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(uw_mig.TRAJECTORY_COLUMNS)
        for code in range(100, 100 + locations):
            for year in years:
                for trajectory in range(1, trajectories + 1):
                    writer.writerow((code, year, year, trajectory, value))
    return path


def write_draw_csv(path, *, codes=(100, 200), years=(2023, 2024), trajectories=2):
    """The source archive's actual order: location, trajectory, then year."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(uw_mig.TRAJECTORY_COLUMNS)
        for code in codes:
            for trajectory in range(1, trajectories + 1):
                for year in years:
                    value = code / 100_000 + trajectory / 10_000 + (year - years[0]) / 1_000
                    writer.writerow((code, year, year, trajectory, value))
    return path


def residual(locations=2, years=3):
    """A migration residual with a recognisable young-adult peak."""
    out = np.zeros((years, locations, cohort.N_SEXES, cohort.N_AGES))
    ages = np.arange(cohort.N_AGES)
    profile = np.exp(-0.5 * ((ages - 25) / 8.0) ** 2)
    for t in range(years):
        for l in range(locations):
            out[t, l, cohort.FEMALE] = profile * (1.0 + l)
            out[t, l, cohort.MALE] = profile * (1.5 + l)
    return out


# --- reading the source -------------------------------------------------------


def test_a_short_location_list_is_rejected(tmp_path):
    path = write_csv(tmp_path / "mig.csv")
    with pytest.raises(uw_mig.MigrationIngestError, match="expected 236 locations"):
        uw_mig.read_trajectories(path)


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(uw_mig.MigrationIngestError, match="not found"):
        uw_mig.read_trajectories(tmp_path / "absent.csv")


def test_implausible_rates_are_rejected(tmp_path, monkeypatch):
    """A file of counts rather than rates must not be mistaken for rates."""
    monkeypatch.setattr(uw_mig, "EXPECTED_LOCATIONS", 2)
    monkeypatch.setattr(uw_mig, "EXPECTED_TRAJECTORIES", 2)
    monkeypatch.setattr(uw_mig, "FORECAST_END", 2024)
    path = write_csv(tmp_path / "mig.csv", value=25000.0)
    with pytest.raises(uw_mig.MigrationIngestError, match="not annual rates"):
        uw_mig.read_trajectories(path)


def test_a_complete_small_grid_reduces_to_medians(tmp_path, monkeypatch):
    monkeypatch.setattr(uw_mig, "EXPECTED_LOCATIONS", 2)
    monkeypatch.setattr(uw_mig, "EXPECTED_TRAJECTORIES", 2)
    monkeypatch.setattr(uw_mig, "FORECAST_END", 2024)
    path = write_csv(tmp_path / "mig.csv", value=0.02)
    rates = uw_mig.read_trajectories(path)
    assert rates.rates.shape == (2, 2)
    assert rates.rates == pytest.approx(0.02)
    assert rates.provenance["reduction"].startswith("median")


def test_all_draws_are_reshaped_and_checked_against_the_median(tmp_path):
    path = write_draw_csv(tmp_path / "mig.csv")
    median = uw_mig.MigrationRates(
        years=np.array([2023, 2024]),
        loc_id=np.array([100, 200]),
        rates=np.array([[0.00115, 0.00215], [0.00215, 0.00315]]),
        provenance={"source": "synthetic"},
    )
    draws = uw_mig.read_rate_draws(path, median)
    assert draws.rates.shape == (2, 2, 2)
    assert draws.rates[0, :, 0] == pytest.approx([0.0011, 0.0021])
    assert draws.rates[1, :, 1] == pytest.approx([0.0022, 0.0032])
    assert "not coupled" in draws.provenance["draw_axis"]


def test_draw_reader_refuses_the_wrong_row_order(tmp_path):
    path = write_csv(tmp_path / "mig.csv")
    median = uw_mig.MigrationRates(
        years=np.array([2023, 2024]),
        loc_id=np.array([100, 101]),
        rates=np.full((2, 2), 0.01),
        provenance={},
    )
    with pytest.raises(uw_mig.MigrationIngestError, match="row order"):
        uw_mig.read_rate_draws(path, median)


# --- the borrowed age composition --------------------------------------------


def test_composition_sums_to_one_per_country():
    shares = uw_mig.age_sex_composition(residual())
    assert shares.shape == (2, cohort.N_SEXES, cohort.N_AGES)
    assert shares.sum(axis=(1, 2)) == pytest.approx(1.0)
    assert np.all(shares >= 0)


def test_composition_keeps_the_young_adult_peak():
    shares = uw_mig.age_sex_composition(residual())
    peak = int(np.argmax(shares[0].sum(axis=0)))
    assert 18 <= peak <= 32


def test_composition_survives_a_country_whose_net_migration_cancels():
    """The reason for normalising on absolute flows rather than the net.

    A country with a large inflow of the young and an equal outflow of the old
    has a net of zero. Dividing by that net is a division by nothing; dividing
    by the gross is not.
    """
    values = residual(locations=1, years=2)
    values[:, 0, cohort.MALE] *= -1.0
    values[:, 0, cohort.MALE] *= (
        values[:, 0, cohort.FEMALE].sum() / np.abs(values[:, 0, cohort.MALE]).sum()
    )
    assert values.sum() == pytest.approx(0.0, abs=1e-9)
    shares = uw_mig.age_sex_composition(values)
    assert shares.sum() == pytest.approx(1.0)
    assert np.all(np.isfinite(shares))


def test_a_country_with_no_residual_at_all_is_refused():
    values = residual(locations=2)
    values[:, 1] = 0.0
    with pytest.raises(uw_mig.MigrationIngestError, match="no age composition"):
        uw_mig.age_sex_composition(values)


# --- rates to engine migration ------------------------------------------------


def make_rates(years=(2024, 2025, 2026), codes=(100, 200), value=0.01):
    return uw_mig.MigrationRates(
        years=np.array(years, dtype=np.int64),
        loc_id=np.array(codes, dtype=np.int64),
        rates=np.full((len(years), len(codes)), value),
        provenance={"reduction": "median"},
    )


def test_net_migrants_are_the_rate_times_the_population():
    rates = make_rates(value=0.01)
    composition = uw_mig.age_sex_composition(residual())
    population = np.full((3, 2), 1_000_000.0)
    assumption = uw_mig.build_assumption(
        rates,
        composition=composition,
        population=population,
        loc_id=np.array([100, 200]),
        locations=("AAA", "BBB"),
        years=np.array([2024, 2025, 2026]),
    )
    assert assumption.values.sum(axis=(2, 3)) == pytest.approx(10_000.0)


def test_negative_rates_produce_net_emigration():
    rates = make_rates(value=-0.005)
    assumption = uw_mig.build_assumption(
        rates,
        composition=uw_mig.age_sex_composition(residual()),
        population=np.full((3, 2), 2_000_000.0),
        loc_id=np.array([100, 200]),
        locations=("AAA", "BBB"),
        years=np.array([2024, 2025, 2026]),
    )
    assert assumption.values.sum(axis=(2, 3)) == pytest.approx(-10_000.0)


def test_the_result_is_labelled_a_scenario_knob_with_a_hold_last_extension():
    assumption = uw_mig.build_assumption(
        make_rates(),
        composition=uw_mig.age_sex_composition(residual()),
        population=np.full((3, 2), 1e6),
        loc_id=np.array([100, 200]),
        locations=("AAA", "BBB"),
        years=np.array([2024, 2025, 2026]),
    )
    assert assumption.independently_sourced is False
    assert "not an independent estimate" in assumption.scenario_knob
    assert assumption.extension.mode == "hold-last"
    assert isinstance(assumption.extension, SeriesExtension)


def test_a_country_the_source_does_not_cover_raises():
    with pytest.raises(uw_mig.MigrationIngestError, match="no trajectories"):
        uw_mig.build_assumption(
            make_rates(),
            composition=uw_mig.age_sex_composition(residual()),
            population=np.full((3, 2), 1e6),
            loc_id=np.array([100, 999]),
            locations=("AAA", "ZZZ"),
            years=np.array([2024, 2025, 2026]),
        )


def test_years_past_the_source_hold_its_final_rate():
    rates = make_rates(years=(2024, 2025), value=0.01)
    assumption = uw_mig.build_assumption(
        rates,
        composition=uw_mig.age_sex_composition(residual()),
        population=np.full((4, 2), 1e6),
        loc_id=np.array([100, 200]),
        locations=("AAA", "BBB"),
        years=np.array([2024, 2025, 2026, 2027]),
    )
    totals = assumption.values.sum(axis=(2, 3))
    assert totals[-1] == pytest.approx(totals[1])


def test_migration_is_accepted_by_the_engine():
    assumption = uw_mig.build_assumption(
        make_rates(),
        composition=uw_mig.age_sex_composition(residual()),
        population=np.full((3, 2), 1e6),
        loc_id=np.array([100, 200]),
        locations=("AAA", "BBB"),
        years=np.array([2024, 2025, 2026]),
    )
    pop = np.full((2, cohort.N_SEXES, cohort.N_AGES), 5000.0)
    sx = np.full((2, cohort.N_SEXES, cohort.N_AGES), 0.99)
    asfr = np.zeros((2, cohort.N_AGES))
    asfr[:, 25] = 0.1
    nxt, births = cohort.step(pop, sx, asfr, np.full(2, 1.05), assumption.values[0])
    assert np.all(nxt >= 0) and np.all(np.isfinite(nxt))
    assert np.all(births > 0)

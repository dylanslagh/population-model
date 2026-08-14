"""Checks for the post-2100 stochastic migration continuation."""

from __future__ import annotations

import numpy as np
import pytest

from popmodel import migration
from popmodel.engine import cohort
from popmodel.ingest import uw_mig


def synthetic_draws(*, seed=7, n_draws=400):
    years = np.arange(2070, 2101)
    mu = np.array([0.01, -0.005])
    phi = np.array([0.7, 0.9])
    sigma = np.array([0.003, 0.005])
    rng = np.random.default_rng(seed)
    rates = np.empty((n_draws, len(years), 2), dtype=np.float32)
    rates[:, 0, :] = mu + rng.normal(0, sigma / np.sqrt(1 - phi**2), (n_draws, 2))
    for t in range(1, len(years)):
        rates[:, t, :] = mu + phi * (rates[:, t - 1, :] - mu) + rng.normal(
            0, sigma, (n_draws, 2)
        )
    return uw_mig.MigrationRateDraws(
        years=years,
        loc_id=np.array([100, 200]),
        trajectory_ids=np.arange(1, n_draws + 1),
        rates=rates,
        provenance={"source": "synthetic"},
    ), mu, phi, sigma


def test_late_ar1_fit_recovers_the_generating_process():
    draws, mu, phi, sigma = synthetic_draws()
    fitted = migration.fit_late_ar1(draws, fit_start_year=2070)
    assert fitted.mu == pytest.approx(mu, abs=0.0015)
    assert fitted.phi == pytest.approx(phi, abs=0.03)
    assert fitted.sigma == pytest.approx(sigma, rel=0.05)


def test_continuation_starts_at_source_boundary_and_is_reproducible():
    draws, *_ = synthetic_draws(n_draws=20)
    fitted = migration.fit_late_ar1(draws, fit_start_year=2070)
    first = migration.simulate_ar1_continuation(draws, fitted, end_rate_year=2105, seed=11)
    second = migration.simulate_ar1_continuation(draws, fitted, end_rate_year=2105, seed=11)
    assert np.array_equal(first.years, np.arange(2100, 2106))
    assert first.rates[:, 0, :] == pytest.approx(draws.rates[:, -1, :])
    assert np.array_equal(first.rates, second.rates)
    assert np.any(first.rates[:, -1, :] != first.rates[:, 0, :])


def test_population_weighted_balancing_is_exact_and_respects_inactive_locations():
    rates = np.array([[0.10, -0.02, 0.25], [-0.04, 0.01, -0.25]])
    population = np.array([[100.0, 900.0, 10.0], [400.0, 600.0, 10.0]])
    adjusted, counts = migration.balance_rates(
        rates, population, active=np.array([True, True, False])
    )
    assert counts.sum(axis=1) == pytest.approx(0.0, abs=1e-10)
    assert adjusted[:, 2] == pytest.approx(0.0)
    assert counts[:, 2] == pytest.approx(0.0)


def test_balancing_honours_outflow_bounds():
    adjusted, counts = migration.balance_rates(
        np.array([[-0.4, 0.1]]),
        np.array([[10.0, 1000.0]]),
        lower=np.array([[-0.01, -0.5]]),
        upper=0.5,
    )
    assert adjusted[0, 0] >= -0.01
    assert counts.sum() == pytest.approx(0.0, abs=1e-10)


def test_age_sex_allocation_redistributes_impossible_emigration_cells():
    available = np.zeros((1, 1, cohort.N_SEXES, cohort.N_AGES))
    available[0, 0, cohort.FEMALE, 20] = 2.0
    available[0, 0, cohort.FEMALE, 30] = 98.0
    shares = np.zeros((1, cohort.N_SEXES, cohort.N_AGES))
    shares[0, cohort.FEMALE, 20] = 0.9
    shares[0, cohort.FEMALE, 30] = 0.1
    movement, redistributed = migration.allocate_age_sex_migration(
        np.array([[-50.0]]), available, shares
    )
    assert movement.sum() == pytest.approx(-50.0)
    assert movement[0, 0, cohort.FEMALE, 20] == pytest.approx(-2.0)
    assert movement[0, 0, cohort.FEMALE, 30] == pytest.approx(-48.0)
    assert redistributed > 0


def test_project_extension_preserves_world_population_when_only_balanced_migration_acts():
    n_draws, n_locations, n_steps = 6, 2, 2
    pop = np.full((n_locations, cohort.N_SEXES, cohort.N_AGES), 100.0)
    sx = np.ones_like(pop)
    asfr = np.zeros((n_locations, cohort.N_AGES))
    srb = np.full(n_locations, 1.05)
    composition = np.zeros_like(pop)
    composition[:, cohort.FEMALE, 25] = 0.5
    composition[:, cohort.MALE, 25] = 0.5
    rates = np.zeros((n_draws, n_steps, n_locations))
    rates[:, :, 0] = np.linspace(-0.02, 0.02, n_draws)[:, None]
    rates[:, :, 1] = -rates[:, :, 0]

    result = migration.project_extension(
        pop,
        start_year=2100,
        end_year=2102,
        sx=sx,
        asfr=asfr,
        srb=srb,
        rate_years=np.array([2100, 2101]),
        rate_paths=rates,
        composition=composition,
        locations=("AAA", "BBB"),
        trajectory_ids=np.arange(n_draws),
        batch_size=3,
    )
    assert result.location_totals.shape == (n_draws, 3, n_locations)
    assert np.diff(result.world, axis=1) == pytest.approx(0.0, abs=1e-8)
    assert result.maximum_world_imbalance_people < 1e-8

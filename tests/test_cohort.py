"""Engine tests on made-up populations with answers worked out by hand.

These run in under a second and need no downloaded data. They are the ones that
catch a broken edit immediately. The test against real UN numbers lives in
scripts/validate_engine.py, because it needs a gigabyte of source files.

Every case here has an answer derived independently of the code: an analytic
growth rate, a conservation law, or arithmetic simple enough to check on paper.
A test whose expected value came from running the function is not a test.
"""

from __future__ import annotations

import numpy as np
import pytest

from popmodel.engine import cohort


def flat_inputs(n_years=1, n_loc=1, survival=1.0, asfr_value=0.0, srb=1.0):
    """Rates where nobody dies and every woman aged 20-29 has the same rate."""
    sx = np.full((n_years, n_loc, 2, cohort.N_AGES), survival)
    asfr = np.zeros((n_years, n_loc, cohort.N_AGES))
    asfr[:, :, 20:30] = asfr_value
    srb_arr = np.full((n_years, n_loc), srb)
    return sx, asfr, srb_arr


def test_nobody_dies_nobody_is_born_population_is_conserved():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 30] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=50)
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=50)
    # Survival 1, fertility 0: the same 2000 people, just older each year.
    assert np.allclose(run.world, 2000.0)
    assert run.population[10, 0, 0, 40] == pytest.approx(1000.0)
    assert run.births.sum() == 0.0
    assert run.deaths.sum() == pytest.approx(0.0, abs=1e-9)


def test_open_age_group_absorbs_and_does_not_leak():
    """Everyone piles into 100+ and stays there when survival is 1."""
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 98] = 500.0
    pop[0, :, 100] = 700.0
    sx, asfr, srb = flat_inputs(n_years=5)
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=5)
    assert np.allclose(run.world, 2400.0)
    # After two steps the 98-year-olds are 100, joining those already there.
    assert run.population[2, 0, 0, 100] == pytest.approx(1200.0)


def test_half_the_hundred_plus_group_dies_each_year():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 100] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=3, survival=0.5)
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=3)
    assert run.population[1, 0, 0, 100] == pytest.approx(500.0)
    assert run.population[3, 0, 0, 100] == pytest.approx(125.0)


def test_births_use_mid_year_women_not_january_women():
    """The half-and-half exposure rule, checked by hand on one cohort.

    1000 women turn 20 during the year: they are 19 on 1 January and 20 on the
    next. With a rate of 0.1 at age 20 they contribute 0.5 * 1000 * 0.1 = 50
    births, not 100 and not 0.
    """
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, cohort.FEMALE, 19] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=1, asfr_value=0.0)
    asfr[0, 0, 20] = 0.1
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=1)
    assert run.births[0, 0] == pytest.approx(50.0)


def test_sex_ratio_at_birth_splits_babies_correctly():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, cohort.FEMALE, 25] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=1, asfr_value=0.2, srb=1.05)
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=1)
    births = run.births[0, 0]
    girls = run.population[1, 0, cohort.FEMALE, 0]
    boys = run.population[1, 0, cohort.MALE, 0]
    assert girls + boys == pytest.approx(births)
    assert boys / girls == pytest.approx(1.05)


def test_growth_rate_matches_the_analytic_answer():
    """A closed population with fixed rates settles onto a fixed growth rate.

    Stable population theory says the long-run annual growth factor is the
    dominant eigenvalue of the projection matrix. Here we check the engine
    against the eigenvalue rather than against itself.
    """
    n_ages = cohort.N_AGES
    survival, rate = 0.99, 0.09
    sx, asfr, srb = flat_inputs(n_years=400, survival=survival, asfr_value=rate, srb=1.0)

    # Build the same one-sex projection matrix explicitly and take its
    # dominant eigenvalue. Female line only, which is what drives growth.
    m = np.zeros((n_ages, n_ages))
    for a in range(1, n_ages):
        m[a, a - 1] = survival
    m[n_ages - 1, n_ages - 1] = survival
    female_share = 0.5
    for a in range(n_ages):
        contrib = 0.0
        if 20 <= a < 30:
            contrib += 0.5 * (asfr[0, 0, a]) * survival * female_share
        if 20 <= a + 1 < 30:
            contrib += 0.5 * (asfr[0, 0, a + 1]) * survival * female_share
        m[0, a] += contrib
    eig = np.abs(np.linalg.eigvals(m)).max()

    pop = np.zeros((1, 2, n_ages))
    pop[0, :, 0:60] = 1000.0
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=400)
    observed = run.world[-1] / run.world[-2]
    assert observed == pytest.approx(eig, rel=1e-6)


def test_migration_is_added_exactly():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 30] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=1)
    mig = np.zeros((1, 1, 2, cohort.N_AGES))
    mig[0, 0, cohort.MALE, 31] = 250.0
    mig[0, 0, cohort.FEMALE, 31] = -100.0
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, migration=mig, n_years=1)
    assert run.population[1, 0, cohort.MALE, 31] == pytest.approx(1250.0)
    assert run.population[1, 0, cohort.FEMALE, 31] == pytest.approx(900.0)
    assert run.world[1] == pytest.approx(2150.0)


def test_population_never_goes_negative():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 30] = 10.0
    sx, asfr, srb = flat_inputs(n_years=1)
    mig = np.zeros((1, 1, 2, cohort.N_AGES))
    mig[0, 0, :, 31] = -1000.0  # more emigrants than people
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, migration=mig, n_years=1)
    assert (run.population >= 0).all()


def test_the_accounting_identity_holds():
    """Population in, plus births, plus migrants, minus deaths, is population out."""
    rng = np.random.default_rng(0)
    pop = rng.uniform(0, 1000, (4, 2, cohort.N_AGES))
    sx = rng.uniform(0.9, 1.0, (3, 4, 2, cohort.N_AGES))
    asfr = np.zeros((3, 4, cohort.N_AGES))
    asfr[:, :, 15:50] = rng.uniform(0, 0.2, (3, 4, 35))
    srb = np.full((3, 4), 1.05)
    mig = rng.normal(0, 20, (3, 4, 2, cohort.N_AGES))
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, migration=mig, n_years=3)
    for t in range(3):
        start = run.population[t].sum(axis=(1, 2))
        end = run.population[t + 1].sum(axis=(1, 2))
        expected = start + run.births[t] + mig[t].sum(axis=(1, 2)) - run.deaths[t]
        assert np.allclose(end, expected)


def test_rates_are_held_constant_past_the_end_of_the_supplied_series():
    pop = np.zeros((1, 2, cohort.N_AGES))
    pop[0, :, 30] = 1000.0
    sx, asfr, srb = flat_inputs(n_years=2, survival=0.5)
    run = cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=6)
    assert run.world[6] == pytest.approx(2000.0 * 0.5**6)


def test_fertility_outside_childbearing_ages_is_refused():
    pop = np.zeros((1, 2, cohort.N_AGES))
    sx, asfr, srb = flat_inputs(n_years=1)
    asfr[0, 0, 5] = 0.1
    with pytest.raises(ValueError, match="outside ages"):
        cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=1)


def test_wrong_shapes_are_refused():
    pop = np.zeros((2, 2, cohort.N_AGES))
    sx, asfr, srb = flat_inputs(n_years=1, n_loc=1)  # one location, not two
    with pytest.raises(ValueError, match="sx must be"):
        cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=1)


def test_negative_and_nonfinite_rates_are_refused():
    pop = np.zeros((1, 2, cohort.N_AGES))
    sx, asfr, srb = flat_inputs(n_years=1)
    sx[0, 0, 0, 10] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        cohort.project(pop, start_year=2000, sx=sx, asfr=asfr, srb=srb, n_years=1)


def test_tfr_is_the_sum_of_single_age_rates():
    asfr = np.zeros(cohort.N_AGES)
    asfr[20:30] = 0.2
    assert cohort.tfr(asfr) == pytest.approx(2.0)

"""Checks for the shared-path migration bridge used by paired selection runs."""

from __future__ import annotations

import numpy as np
import pytest

from popmodel import migration
from popmodel.engine import cohort
from popmodel.mech import engine as mech_engine


def raw_path(years=(2024,)):
    return migration.RawMigrationPath(
        years=np.asarray(years),
        loc_id=np.array([1, 2]),
        trajectory_id=17,
        rates=np.array([[0.02, -0.01] for _ in years]),
        continuation_seed=23,
    )


def policy(years=(2024,)):
    composition = np.full((2, cohort.N_SEXES, cohort.N_AGES), 1 / (2 * cohort.N_AGES))
    return migration.BalancedMigrationPath(
        raw=raw_path(years),
        rates=raw_path(years).rates,
        composition=composition,
        active_locations=np.array([True, True]),
        locations=("AAA", "BBB"),
    )


def aged_one_year(pop, sx):
    aged = np.zeros_like(pop)
    aged[:, :, 1:cohort.MAX_AGE] = pop[:, :, :cohort.MAX_AGE - 1] * sx[:, :, 1:cohort.MAX_AGE]
    aged[:, :, cohort.MAX_AGE] = (pop[:, :, cohort.MAX_AGE - 1] + pop[:, :, cohort.MAX_AGE]) * sx[:, :, cohort.MAX_AGE]
    return aged


def test_policy_balances_the_shared_raw_path_and_records_its_adjustment():
    p = policy()
    start = np.array([1_000.0, 3_000.0])
    available = np.full((2, cohort.N_SEXES, cohort.N_AGES), 20.0)
    movement = p.movement(start, available)
    receipt = p.receipt()

    assert movement.sum() == pytest.approx(0.0, abs=1e-8)
    assert receipt["source_trajectory_id"] == 17
    assert receipt["continuation_seed"] == 23
    assert receipt["maximum_rate_adjustment"] > 0
    assert receipt["maximum_world_imbalance_people"] < 1e-8


def test_neutral_typed_engine_matches_plain_engine_with_state_aware_migration():
    n_loc = 2
    pop = np.full((n_loc, cohort.N_SEXES, cohort.N_AGES), 1_000.0)
    sx = np.full((1, n_loc, cohort.N_SEXES, cohort.N_AGES), 0.995)
    sx[:, :, :, 0] = 0.997
    sx[:, :, :, cohort.MAX_AGE] = 0.6
    asfr = np.zeros((1, n_loc, cohort.N_AGES))
    asfr[:, :, 20:41] = 1.8 / 21
    srb = np.full((1, n_loc), 1.05)

    direct_policy = policy()
    direct_movement = direct_policy.movement(
        pop.sum(axis=(1, 2)), aged_one_year(pop, sx[0])
    )
    plain = cohort.project(
        pop, start_year=2024, sx=sx, asfr=asfr, srb=srb,
        migration=direct_movement[None], n_years=1,
    )

    typed = np.repeat(pop[:, None] / 2, 2, axis=1)
    paired_policy = policy()
    result = mech_engine.project(
        typed, start_year=2024, sx=sx, asfr=asfr, srb=srb,
        propensity=np.ones((n_loc, 2)), transition=np.tile(np.eye(2)[None], (n_loc, 1, 1)),
        environment=np.ones((1, n_loc)), labels=("a", "b"), locations=("AAA", "BBB"),
        migration=paired_policy, n_years=1,
    )

    assert result.population == pytest.approx(plain.location_totals(), rel=1e-12)
    assert paired_policy.receipt()["maximum_world_imbalance_people"] < 1e-8

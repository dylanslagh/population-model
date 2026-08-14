"""Tests for the mechanistic layer.

Three of these matter more than the rest:

* `test_neutral_types_reproduce_the_ordinary_engine` -- if the typed engine is
  not identical to the plain one when the mechanism is switched off, then any
  difference between Phase 4 and Phase 5 might be a second implementation of
  the arithmetic rather than the mechanism.
* `test_one_generation_matches_the_breeders_equation` -- the mechanism has a
  known closed-form answer for one generation. If the code disagrees with it,
  the code is wrong, and it will be wrong in a direction nobody notices because
  the output still looks like a population projection.
* `test_anchored_transmission_selects_more_slowly` -- the first version of this
  module regressed children toward the base-year composition without anyone
  deciding to, and produced roughly a quarter of the selection the theory
  predicts. Both rules are kept, and this pins the difference.
"""

from __future__ import annotations

import numpy as np
import pytest

from popmodel.engine import cohort
from popmodel.mech import composition, engine as mech_engine, environment
from popmodel.mech import parameters as mech_parameters
from popmodel.mech.parameters import Parameter, ParameterError, ParameterSet


def parameter(name="p", value=0.5, low=0.0, high=1.0, kind="sourced",
              verified=False, evidence="a study", provenance="recorded by hand"):
    return Parameter(
        name=name, value=value, low=low, high=high, unit="proportion", kind=kind,
        verified=verified, evidence=evidence, provenance=provenance, notes="",
    )


def rates(n_loc=4, n_years=30, tfr=1.8):
    """Simple, valid demographic rates. Not realistic; realistic is not the point."""
    asfr = np.zeros((n_years, n_loc, cohort.N_AGES))
    ages = np.arange(cohort.FERT_AGE_MIN, cohort.FERT_AGE_MAX + 1)
    bell = np.exp(-0.5 * ((ages - 28) / 6.0) ** 2)
    asfr[:, :, cohort.FERT_AGE_MIN:cohort.FERT_AGE_MAX + 1] = bell / bell.sum() * tfr
    sx = np.full((n_years, n_loc, cohort.N_SEXES, cohort.N_AGES), 0.995)
    sx[:, :, :, 0] = 0.997
    sx[:, :, :, 100] = 0.6
    srb = np.full((n_years, n_loc), 1.05)
    pop = np.full((n_loc, cohort.N_SEXES, cohort.N_AGES), 100_000.0)
    return pop, sx, asfr, srb


# --- the structural check ------------------------------------------------------


def test_neutral_types_reproduce_the_ordinary_engine():
    pop, sx, asfr, srb = rates()
    n_loc, n_years = pop.shape[0], sx.shape[0]
    loc = tuple(f"C{i}" for i in range(n_loc))

    plain = cohort.project(
        pop, start_year=2024, sx=sx, asfr=asfr, srb=srb,
        locations=list(loc), n_years=n_years,
    )

    shares = np.array([0.2, 0.5, 0.3])
    typed = pop[:, None, :, :] * shares[None, :, None, None]
    result = mech_engine.project(
        typed, start_year=2024, sx=sx, asfr=asfr, srb=srb,
        propensity=np.ones((n_loc, 3)),
        transition=np.tile(np.eye(3)[None], (n_loc, 1, 1)),
        environment=np.ones((n_years, n_loc)),
        labels=("a", "b", "c"), locations=loc, n_years=n_years,
    )

    expected = plain.location_totals()
    assert result.population == pytest.approx(expected, rel=1e-12)
    assert result.observed_tfr == pytest.approx(asfr.sum(axis=2), rel=1e-12)
    assert result.selection_effect() == pytest.approx(1.0)


def test_selection_switched_off_leaves_fertility_exactly_alone():
    pop, sx, asfr, srb = rates()
    n_loc, n_years = pop.shape[0], sx.shape[0]
    shares = np.full(3, 1 / 3)
    result = mech_engine.project(
        pop[:, None, :, :] * shares[None, :, None, None],
        start_year=2024, sx=sx, asfr=asfr, srb=srb,
        propensity=np.ones((n_loc, 3)),
        transition=np.tile(
            composition.mainstream_transition(3, 0.4, shares)[None], (n_loc, 1, 1)
        ),
        environment=np.ones((n_years, n_loc)),
        labels=("a", "b", "c"), locations=tuple(f"C{i}" for i in range(n_loc)),
        n_years=n_years,
    )
    # Composition may move; with equal propensities it cannot move fertility.
    assert result.selection_effect() == pytest.approx(1.0, abs=1e-12)


# --- the mechanism against its own theory --------------------------------------


def test_one_generation_matches_the_breeders_equation():
    """Selection should move the mean by persistence x variance / mean.

    That is the standard evolutionary-demography result and the calculation
    spec section 6.8 quotes. Doing it on the composition directly, rather than
    through the engine, isolates the mechanism from the demography.
    """
    persistence, cv = 0.15, 0.6
    propensity = composition.propensity_bins(3, cv)
    shares = np.full(3, 1 / 3)
    rule = composition.TransitionRule(
        persistence=persistence,
        base_share=shares[None, :],
        mainstream=np.ones(3, dtype=bool),
        fixed_rows=np.zeros((1, 3, 3)),
        mode="population",
    )

    mean = float(shares @ propensity)
    variance = float(shares @ (propensity - mean) ** 2)
    # Parents contribute in proportion to how many children they have.
    birth_weighted = shares * propensity / (shares @ propensity)
    child_shares = birth_weighted @ rule.matrix(shares[None, :])[0]
    moved = float(child_shares @ propensity) - mean

    assert moved == pytest.approx(persistence * variance / mean, rel=1e-9)
    assert moved > 0


def test_anchored_transmission_selects_more_slowly():
    propensity = composition.propensity_bins(3, 0.6)
    shares = np.full(3, 1 / 3)
    fixed = np.zeros((1, 3, 3))

    def advance(mode, generations=4):
        rule = composition.TransitionRule(
            persistence=0.15, base_share=shares[None, :],
            mainstream=np.ones(3, dtype=bool), fixed_rows=fixed, mode=mode,
        )
        current = shares.copy()
        for _ in range(generations):
            weighted = current * propensity / (current @ propensity)
            current = weighted @ rule.matrix(current[None, :])[0]
        return float(current @ propensity)

    population = advance("population")
    anchored = advance("anchored")
    assert population > anchored > 1.0
    # The structural choice is worth a large fraction of the whole effect.
    assert (population - 1.0) > 1.5 * (anchored - 1.0)


def test_the_toy_demonstration_compounds():
    shares = composition.toy_demonstration()
    assert len(shares) == 4
    assert all(b > a for a, b in zip(shares, shares[1:]))
    assert 0.55 < shares[-1] < 0.75  # spec 6.6 says "near 70%"


def test_retention_matters_as_much_as_fertility():
    """Spec 6.6's actual claim, tested rather than asserted."""
    high_fertility_leaky = composition.toy_demonstration(
        group_fertility=6.0, retention=0.55
    )
    lower_fertility_tight = composition.toy_demonstration(
        group_fertility=4.5, retention=0.95
    )
    assert lower_fertility_tight[-1] > high_fertility_leaky[-1]


# --- composition ---------------------------------------------------------------


@pytest.mark.parametrize("cv", [0.3, 0.6, 0.9])
def test_propensity_bins_have_the_requested_mean_and_spread(cv):
    values = composition.propensity_bins(3, cv)
    assert values.mean() == pytest.approx(1.0)
    assert values.std() == pytest.approx(cv, rel=1e-6)
    assert np.all(values > 0)
    assert np.all(np.diff(values) > 0)


def test_a_spread_that_would_go_negative_is_refused():
    with pytest.raises(ParameterError, match="negative fertility propensity"):
        composition.propensity_bins(2, 1.9)


@pytest.mark.parametrize("mode", ["population", "anchored"])
def test_transition_rows_are_probability_distributions(mode):
    shares = np.array([[0.2, 0.5, 0.3]])
    rule = composition.TransitionRule(
        persistence=0.25, base_share=shares, mainstream=np.ones(3, dtype=bool),
        fixed_rows=np.zeros((1, 3, 3)), mode=mode,
    )
    matrix = rule.matrix(np.array([[0.1, 0.3, 0.6]]))
    assert matrix.sum(axis=2) == pytest.approx(1.0)
    assert np.all(matrix >= 0)


def test_a_named_group_keeps_the_base_year_anchored():
    parameters = mech_parameters.load()
    group = composition.named_groups(parameters)["ISR"]
    system = composition.build(parameters, group=group, country_fertility=2.85)
    # The TypeSystem constructor enforces it, so reaching here is the assertion;
    # this states why it matters.
    assert system.share @ system.propensity == pytest.approx(1.0)
    assert system.group_index == 3
    assert system.transition[3, 3] == pytest.approx(group.retention)
    assert system.transition[3, :3].sum() == pytest.approx(1 - group.retention)


def test_a_group_larger_than_the_country_can_support_is_refused():
    parameters = mech_parameters.load()
    monster = composition.NamedGroup(
        key="x", label="x", iso3="ZZZ", share=0.5, fertility=9.0, retention=0.9
    )
    with pytest.raises(ParameterError, match="leaves nothing for everyone else"):
        composition.build(parameters, group=monster, country_fertility=1.5)


def test_defectors_land_in_the_mainstream_not_in_nothing():
    parameters = mech_parameters.load()
    group = composition.named_groups(parameters)["USA"]
    system = composition.build(parameters, group=group, country_fertility=1.62)
    leaving = system.transition[system.group_index, :3]
    assert leaving.sum() > 0
    # Weighted toward the high-propensity type, per spec 6.5.
    assert leaving[2] > leaving[0]


# --- the environment -----------------------------------------------------------


def test_mean_reversion_is_the_uns_own_path_untouched():
    parameters = mech_parameters.load()
    years = np.arange(2024, 2054)
    tfr = np.linspace(2.0, 1.6, len(years))[:, None] * np.ones((1, 2))
    env = environment.build(
        "mean-reversion", years=years, locations=("A", "B"),
        reference_tfr=tfr, parameters=parameters,
    )
    assert env.multiplier == pytest.approx(1.0)


def test_stable_low_removes_a_rebound_but_keeps_the_descent():
    parameters = mech_parameters.load()
    years = np.arange(2024, 2034)
    path = np.array([2.0, 1.8, 1.6, 1.4, 1.3, 1.4, 1.6, 1.8, 1.9, 2.0])
    tfr = path[:, None]
    env = environment.build(
        "stable-low", years=years, locations=("A",),
        reference_tfr=tfr, parameters=parameters,
    )
    effective = env.multiplier[:, 0] * path
    assert effective[:5] == pytest.approx(path[:5])  # the way down is kept
    assert effective[5:] == pytest.approx(1.3)  # the rebound is not


def test_continued_pressure_declines_and_then_stops_at_its_floor():
    parameters = mech_parameters.load()
    years = np.arange(2024, 2200)
    tfr = np.full((len(years), 1), 1.8)
    env = environment.build(
        "continued-pressure", years=years, locations=("A",),
        reference_tfr=tfr, parameters=parameters, pressure_from=2050,
    )
    multiplier = env.multiplier[:, 0]
    assert multiplier[:26] == pytest.approx(1.0)  # nothing before 2050
    assert multiplier[-1] == pytest.approx(parameters.value("development_floor"))
    assert np.all(np.diff(multiplier) <= 1e-12)
    assert "development_decline_per_decade" in env.knobs


# --- the parameter table -------------------------------------------------------


def test_the_committed_table_loads_and_declares_its_own_weakness():
    parameters = mech_parameters.load()
    assert len(parameters.parameters) == 13
    assert len(parameters.knobs) == 5, "a table with no knobs is hiding something"
    assert parameters.verified_fraction == pytest.approx(7 / 13)
    assert parameters.unverified == [
        "defector_high_propensity_weight",
        "development_decline_per_decade",
        "development_floor",
        "group_convergence_per_generation",
        "mainstream_propensity_cv",
        "mainstream_types",
    ]
    assert "unverified" in parameters.caveat()


def test_a_parameter_with_no_provenance_is_refused():
    with pytest.raises(ParameterError, match="where it came from"):
        parameter(provenance="   ")


def test_a_sourced_parameter_with_no_evidence_is_refused():
    with pytest.raises(ParameterError, match="name the evidence"):
        parameter(kind="sourced", evidence="")


def test_a_knob_cannot_claim_to_be_verified():
    with pytest.raises(ParameterError, match="nothing to verify it against"):
        parameter(kind="knob", verified=True, evidence="")


def test_a_value_outside_its_own_range_is_refused():
    with pytest.raises(ParameterError, match="outside its range"):
        parameter(value=2.0, low=0.0, high=1.0)


def test_asking_for_a_parameter_that_does_not_exist_says_so():
    parameters = ParameterSet({"a": parameter(name="a")}, mech_parameters.table_path())
    with pytest.raises(ParameterError, match="rather than hard-coding"):
        parameters.value("b")


def test_drawing_stays_inside_the_stated_range():
    rng = np.random.default_rng(0)
    p = parameter(value=0.5, low=0.2, high=0.8)
    draws = [p.draw(rng) for _ in range(200)]
    assert all(0.2 <= d <= 0.8 for d in draws)
    assert min(draws) < 0.3 and max(draws) > 0.7


# --- engine guards -------------------------------------------------------------


def test_the_engine_refuses_a_population_of_the_wrong_shape():
    pop, sx, asfr, srb = rates()
    with pytest.raises(ValueError, match="pop0 must be"):
        mech_engine.project(
            pop, start_year=2024, sx=sx, asfr=asfr, srb=srb,
            propensity=np.ones((4, 3)), transition=np.tile(np.eye(3)[None], (4, 1, 1)),
            environment=np.ones((30, 4)), labels=("a", "b", "c"),
            locations=("A", "B", "C", "D"),
        )


def test_migration_is_split_across_types_and_conserves_people():
    pop, sx, asfr, srb = rates(n_loc=2, n_years=5)
    shares = np.array([0.5, 0.5])
    typed = pop[:, None, :, :] * shares[None, :, None, None]
    migration = np.zeros((5, 2, cohort.N_SEXES, cohort.N_AGES))
    migration[:, 0, :, 25] = 1000.0

    result = mech_engine.project(
        typed, start_year=2024, sx=sx, asfr=asfr, srb=srb,
        propensity=np.ones((2, 2)), transition=np.tile(np.eye(2)[None], (2, 1, 1)),
        environment=np.ones((5, 2)), labels=("a", "b"), locations=("A", "B"),
        migration=migration, n_years=5,
    )
    assert np.all(np.isfinite(result.population))
    assert result.population[-1, 0] > result.population[-1, 1]
    assert result.composition.sum(axis=2) == pytest.approx(1.0)

"""The projection engine with a composition axis.

This is `engine/cohort.py` with one extra dimension: every country's population
is split across fertility-propensity types, and children are assigned to types
by a transition matrix at birth. Everything else -- ages, survival, the
mid-year exposure, the open-ended age group -- is identical, deliberately, so
that a run with every propensity set to one reproduces the ordinary engine
exactly. The tests check that, because it is the only way to know that a
difference in output came from the mechanism rather than from a second
implementation of the arithmetic.

It still contains no theory about the future. It takes propensities, a
transition matrix and an environment as given and does the bookkeeping. The
theory lives in `composition.py` and `environment.py`, where it can be argued
with.

The one new piece of arithmetic
-------------------------------
Births are counted by the mother's type and then redistributed to the child's
type::

    births_by_mother[l, k] = sum_a  exposure[l, k, female, a] * asfr[l, a]
                                    * environment[l] * propensity[l, k]
    births_by_child[l, j]  = sum_k  births_by_mother[l, k] * transition[l, k, j]

Everything the mechanism claims is in those two lines. Selection is what
happens when the rows of `transition` are not identical and `propensity` is not
constant: the types that have more children pass on more of their type, so the
composition drifts, so the population-average propensity moves, so observed
fertility departs from the environment path without anyone imposing a floor.

Assumptions this version makes, all of them stated
--------------------------------------------------
* Survival is the same for every type. Real high-fertility groups often have
  different mortality; modelling that without evidence would be an epicycle.
* Migrants are distributed across types in proportion to the receiving
  country's current composition. They therefore dilute nothing and concentrate
  nothing, which is a real assumption and probably wrong in both directions.
* Sex ratio at birth is the same for every type.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from popmodel.engine import cohort


@dataclass
class MechResult:
    """What a mechanistic run produces, kept compact on purpose.

    The full state is (years, countries, types, sexes, ages), which is far too
    large to retain for every year of every draw. What is kept is what the
    project's questions actually need: totals, composition, and the observed
    fertility that came out.
    """

    years: np.ndarray  # (T+1,)
    locations: tuple[str, ...]
    labels: tuple[str, ...]
    population: np.ndarray  # (T+1, L) total people
    composition: np.ndarray  # (T+1, L, K) share of each type
    births: np.ndarray  # (T, L)
    observed_tfr: np.ndarray  # (T, L) what the model's fertility actually was
    environment_tfr: np.ndarray  # (T, L) what it would have been without selection

    @property
    def world(self) -> np.ndarray:
        return self.population.sum(axis=1)

    def world_composition(self) -> np.ndarray:
        """(T+1, K) world-wide share of each type, weighted by population."""
        weighted = self.composition * self.population[:, :, None]
        return weighted.sum(axis=1) / self.population.sum(axis=1)[:, None]

    def selection_effect(self) -> np.ndarray:
        """(T, L) observed fertility divided by what the environment alone gives.

        This is the number the project exists to produce. Above one means
        selection has raised fertility above the environment path; below one
        means the composition moved the other way. It is the answer to
        "whether and when selection overtakes the downward environmental
        shift", per spec section 8.
        """
        return np.divide(
            self.observed_tfr,
            self.environment_tfr,
            out=np.ones_like(self.observed_tfr),
            where=self.environment_tfr > 0,
        )


def step(
    pop: np.ndarray,
    sx: np.ndarray,
    asfr: np.ndarray,
    srb: np.ndarray,
    propensity: np.ndarray,
    transition: np.ndarray,
    environment: np.ndarray,
    migration: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance one year, carrying composition.

    Args:
        pop: (L, K, 2, 101) population on 1 January.
        sx: (L, 2, 101) survival ratios, INTO age a, shared across types.
        asfr: (L, 101) the country's base age-specific fertility.
        srb: (L,) sex ratio at birth.
        propensity: (L, K) fertility multiplier for each type.
        transition: (L, K, K) parent type to child type.
        environment: (L,) multiplier on the base fertility, this year.
        migration: (L, 2, 101) net migrants, split across types by composition.

    Returns:
        (population next 1 January, births by child type).
    """
    aged = np.zeros_like(pop)
    aged[:, :, :, 1:cohort.MAX_AGE] = (
        pop[:, :, :, 0:cohort.MAX_AGE - 1] * sx[:, None, :, 1:cohort.MAX_AGE]
    )
    aged[:, :, :, cohort.MAX_AGE] = (
        pop[:, :, :, cohort.MAX_AGE - 1] + pop[:, :, :, cohort.MAX_AGE]
    ) * sx[:, None, :, cohort.MAX_AGE]

    if migration is not None:
        # Split by the receiving population's composition at each age and sex,
        # rather than by its overall composition: a country whose high-fertility
        # type is concentrated among the young should not receive migrants as
        # though it were evenly mixed.
        total = aged.sum(axis=1, keepdims=True)
        share = np.divide(aged, total, out=np.zeros_like(aged), where=total > 0)
        aged = aged + share * migration[:, None, :, :]

    exposure = 0.5 * (pop[:, :, cohort.FEMALE, :] + aged[:, :, cohort.FEMALE, :])
    rate = asfr[:, None, :] * environment[:, None, None] * propensity[:, :, None]
    births_by_mother = np.einsum("lka,lka->lk", exposure, rate)
    births_by_child = np.einsum("lk,lkj->lj", births_by_mother, transition)

    female_share = 1.0 / (1.0 + srb)
    aged[:, :, cohort.FEMALE, 0] += (
        births_by_child * female_share[:, None] * sx[:, None, cohort.FEMALE, 0]
    )
    aged[:, :, cohort.MALE, 0] += (
        births_by_child * (1.0 - female_share)[:, None] * sx[:, None, cohort.MALE, 0]
    )

    np.maximum(aged, 0.0, out=aged)
    return aged, births_by_child


def project(
    pop0: np.ndarray,
    *,
    start_year: int,
    sx: np.ndarray,
    asfr: np.ndarray,
    srb: np.ndarray,
    propensity: np.ndarray,
    transition: np.ndarray,
    environment: np.ndarray,
    labels: tuple[str, ...],
    locations: tuple[str, ...],
    migration: np.ndarray | None = None,
    n_years: int | None = None,
) -> MechResult:
    """Run the mechanistic projection forward.

    `propensity` may be (L, K) or (T, L, K); the second form lets a named
    group's advantage decay as it grows, which spec section 6.7 requires be
    possible. `transition` may likewise be (L, K, K) or (T, L, K, K).

    Rate arrays shorter than `n_years` hold their final year, exactly as the
    ordinary engine does, and that is an assumption a scenario should declare.
    """
    pop0 = np.asarray(pop0, dtype=np.float64)
    n_loc, n_types = pop0.shape[0], pop0.shape[1]
    if pop0.ndim != 4 or pop0.shape[2:] != (cohort.N_SEXES, cohort.N_AGES):
        raise ValueError(f"pop0 must be (L, K, 2, {cohort.N_AGES}); got {pop0.shape}")
    if np.any(pop0 < 0):
        raise ValueError("pop0 contains negative population")
    if len(locations) != n_loc or len(labels) != n_types:
        raise ValueError("labels or locations do not match the population array")

    if n_years is None:
        n_years = min(a.shape[0] for a in (sx, asfr, srb, environment))

    def year_of(arr: np.ndarray, t: int, per_year: bool) -> np.ndarray:
        return arr[min(t, arr.shape[0] - 1)] if per_year else arr

    propensity_by_year = propensity.ndim == 3
    # A rule rebuilds the matrix each year from the current composition, which
    # is what lets selection compound; a plain array is fixed for all time.
    transition_rule = hasattr(transition, "matrix")
    transition_by_year = (not transition_rule) and transition.ndim == 4

    population = np.empty((n_years + 1, n_loc))
    composition = np.empty((n_years + 1, n_loc, n_types))
    births = np.empty((n_years, n_loc))
    observed = np.empty((n_years, n_loc))
    environment_tfr = np.empty((n_years, n_loc))

    state = pop0.copy()
    totals = state.sum(axis=(2, 3))
    population[0] = totals.sum(axis=1)
    composition[0] = totals / np.maximum(population[0][:, None], 1e-12)

    for t in range(n_years):
        sx_t = year_of(sx, t, True)
        asfr_t = year_of(asfr, t, True)
        srb_t = year_of(srb, t, True)
        env_t = year_of(environment, t, True)
        prop_t = year_of(propensity, t, propensity_by_year)
        mig_t = year_of(migration, t, True) if migration is not None else None

        base_tfr = asfr_t.sum(axis=1)
        environment_tfr[t] = base_tfr * env_t
        # The population-average propensity, weighted by women of childbearing
        # age rather than by everybody: it is those women who produce the
        # births, and the age structures of the types differ.
        women = state[:, :, cohort.FEMALE, cohort.FERT_AGE_MIN:cohort.FERT_AGE_MAX + 1]
        weight = women.sum(axis=2)
        weight_total = weight.sum(axis=1, keepdims=True)
        mean_propensity = np.divide(
            (weight * prop_t).sum(axis=1),
            weight_total[:, 0],
            out=np.ones(n_loc),
            where=weight_total[:, 0] > 0,
        )
        observed[t] = environment_tfr[t] * mean_propensity

        if transition_rule:
            # The population a child grows up in is the one alive now, so the
            # ambient mix is the composition of childbearing adults this year.
            ambient = np.divide(
                weight,
                np.maximum(weight_total, 1e-12),
                out=np.zeros_like(weight),
                where=weight_total > 1e-12,
            )
            trans_t = transition.matrix(ambient)
        else:
            trans_t = year_of(transition, t, transition_by_year)

        state, born = step(
            state, sx_t, asfr_t, srb_t, prop_t, trans_t, env_t, mig_t
        )
        births[t] = born.sum(axis=1)
        totals = state.sum(axis=(2, 3))
        population[t + 1] = totals.sum(axis=1)
        composition[t + 1] = totals / np.maximum(population[t + 1][:, None], 1e-12)

    return MechResult(
        years=np.arange(start_year, start_year + n_years + 1),
        locations=tuple(locations),
        labels=tuple(labels),
        population=population,
        composition=composition,
        births=births,
        observed_tfr=observed,
        environment_tfr=environment_tfr,
    )

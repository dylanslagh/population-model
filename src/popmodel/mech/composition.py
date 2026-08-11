"""Who is becoming more common: types, transmission, retention, defection.

Spec section 5.3 asks the project to keep two questions apart, and this module
owns the first of them:

* **Who is becoming more common?** Here.
* **How many children does a person of a given type have under current
  conditions?** That is `environment.py`.

A "type" is a fertility propensity, expressed as a multiplier on the country's
own fertility. Propensity 1.4 means a woman of that type has forty per cent
more children than the national average did in the base year -- it is not a
number of children, and it does not change when the environment does. That
separation is the whole point: selection moves the composition, development
moves the environment, and observed fertility is what comes out.

The mainstream is not a residual bucket
---------------------------------------
Spec section 6.5. Three latent propensity types with no ethnic, religious or
political label, drawn as quantile bins of a right-skewed distribution of
completed family size. Children land near their parents' type more often than
chance, which is what "intergenerational fertility persistence" means, and the
probability of landing in the same type IS the parent-child correlation in
propensity -- see `mainstream_transition`.

Named groups are transitions, not labels
----------------------------------------
Spec section 6.4. A named group is one more type with its own propensity and,
crucially, its own retention: the share of children raised in it who remain in
it as adults. Those who leave do not vanish into an average. They land in the
mainstream, weighted toward its high-propensity type, because leaving a
community is not the same as abandoning everything it taught you.

What this version does not do
-----------------------------
* No conversion *into* named groups. Small for the two groups modelled, and
  inventing a rate would be worse than omitting one.
* No within-group variation in retention. Spec 6.4 asks for it eventually.
* Every type starts with the country's own age structure, which understates
  named groups: a population with six children per woman is far younger than
  its host. This makes the group's growth here a *lower* bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from popmodel.mech.parameters import ParameterError, ParameterSet

MAINSTREAM_LABELS = ("mainstream-low", "mainstream-middle", "mainstream-high")


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_quantile(p: float) -> float:
    """Inverse normal CDF by bisection. Small, exact enough, no new dependency."""
    if not 0.0 < p < 1.0:
        raise ValueError("quantile argument must be strictly between 0 and 1")
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def propensity_bins(n_types: int, cv: float) -> np.ndarray:
    """Propensities for equal-share quantile bins of completed family size.

    The distribution of completed family size is right-skewed -- a floor at
    zero children and a long upper tail -- so a lognormal is used rather than a
    symmetric spread. Each type is the conditional mean within its own
    equal-probability bin.

    Discretising a continuous distribution into a handful of points loses part
    of its dispersion, so the deviations are then rescaled to reproduce the
    requested coefficient of variation exactly. Without that step three types
    would carry about 80% of the spread the evidence describes, and selection
    would be quietly weakened by an implementation detail.
    """
    if n_types < 2:
        raise ParameterError("selection needs at least two propensity types")
    if not 0.0 < cv < 2.0:
        raise ParameterError(f"a propensity coefficient of variation of {cv} is absurd")

    sigma = math.sqrt(math.log1p(cv * cv))
    share = 1.0 / n_types

    # E[X | bin] via the partial expectation of a lognormal with mean one.
    # For a lognormal with mean one, the partial expectation below its own
    # k/K quantile simplifies to Phi(z_k - sigma), where z_k is the standard
    # normal quantile. That identity is why no numerical integration is needed.
    edges = [0.0] + [
        _normal_cdf(_normal_quantile(k * share) - sigma) for k in range(1, n_types)
    ] + [1.0]
    means = np.array(
        [(edges[k + 1] - edges[k]) / share for k in range(n_types)], dtype=np.float64
    )

    realised_cv = float(np.std(means))
    if realised_cv <= 0:
        raise ParameterError("propensity bins collapsed to a single value")
    scaled = 1.0 + (means - 1.0) * (cv / realised_cv)
    if np.any(scaled <= 0):
        raise ParameterError(
            f"a coefficient of variation of {cv} forces a negative fertility "
            f"propensity with {n_types} types; use more types or a smaller spread"
        )
    return scaled


def mainstream_transition(n_types: int, persistence: float, shares: np.ndarray) -> np.ndarray:
    """Parent type to child type, for the unlabelled mainstream.

    A child stays in the parent's type with probability `persistence`, and
    otherwise is drawn from the population's baseline distribution of types.

    That mixture is chosen because its parameter means something measurable:
    since propensity is a deterministic function of type and the alternative
    draw is independent, the resulting parent-child correlation in propensity
    is exactly `persistence`. So the number in the table is the number the
    family studies estimate, with no translation step to get wrong.
    """
    if not 0.0 <= persistence <= 1.0:
        raise ParameterError("persistence must be a probability")
    shares = np.asarray(shares, dtype=np.float64)
    if shares.shape != (n_types,) or abs(shares.sum() - 1.0) > 1e-9:
        raise ParameterError("mainstream shares must be a distribution over the types")
    return persistence * np.eye(n_types) + (1.0 - persistence) * shares[None, :]



TRANSMISSION_MODES = ("population", "anchored")


@dataclass(frozen=True)
class TransitionRule:
    """How a child's type is drawn, given its mother's and its surroundings.

    A child inherits its mother's type with probability `persistence`.
    Otherwise it resembles the population it grows up in -- and *which*
    population that is turns out to matter more than almost anything else in
    the model.

    ``population`` (the default)
        The child is drawn from the current composition. This is the standard
        evolutionary-demography result: the mean propensity then moves by
        ``persistence x variance / mean`` each generation, which is the
        calculation spec section 6.8 quotes at roughly 0.3 children per
        generation. Selection compounds, because the thing children regress
        toward is itself moving.

    ``anchored``
        The child is drawn from the base-year composition, which never moves.
        Selection then runs into an equilibrium where the pull-back cancels it,
        and the long-run effect is several times smaller. This is a coherent
        claim -- that institutions hold the culture in place regardless of who
        is in it -- but it is a claim, and it should be argued for rather than
        arrived at by accident.

    The first implementation of this module used ``anchored`` without noticing,
    and produced a selection effect about a quarter of what the theory predicts.
    Both are kept so the difference can be shown rather than described.

    Children of named-group parents are handled separately: retention is a
    property of the group, not of the surrounding mix, so those rows are fixed.
    No conversion *into* a named group is modelled.
    """

    persistence: float
    base_share: np.ndarray  # (L, K)
    mainstream: np.ndarray  # (K,) boolean
    fixed_rows: np.ndarray  # (L, K, K), used for the non-mainstream rows
    mode: str = "population"

    def __post_init__(self) -> None:
        if self.mode not in TRANSMISSION_MODES:
            raise ParameterError(f"unknown transmission mode {self.mode!r}")
        if not 0.0 <= self.persistence <= 1.0:
            raise ParameterError("persistence must be a probability")

    def matrix(self, ambient: np.ndarray) -> np.ndarray:
        """(L, K, K) for the current composition of childbearing adults."""
        source = self.base_share if self.mode == "anchored" else np.asarray(ambient)
        # Children of mainstream parents stay in the mainstream: the ambient
        # distribution is renormalised over the mainstream types only, so a
        # growing named group does not pull the mainstream's children into it.
        weights = source * self.mainstream[None, :]
        total = weights.sum(axis=1, keepdims=True)
        weights = np.divide(
            weights,
            total,
            out=np.repeat(
                (self.base_share * self.mainstream[None, :])
                / np.maximum((self.base_share * self.mainstream[None, :]).sum(
                    axis=1, keepdims=True), 1e-12),
                1,
                axis=0,
            ),
            where=total > 1e-12,
        )

        n_loc, n_types = self.base_share.shape
        out = np.array(self.fixed_rows, dtype=np.float64, copy=True)
        eye = np.eye(n_types)[None, :, :]
        mainstream_block = (
            self.persistence * eye + (1.0 - self.persistence) * weights[:, None, :]
        )
        rows = self.mainstream[None, :, None]
        out = np.where(rows, mainstream_block, out)
        return out

@dataclass(frozen=True)
class NamedGroup:
    """A high-fertility population modelled explicitly, in one country."""

    key: str
    label: str
    iso3: str
    share: float  # of that country's population in the base year
    fertility: float  # children per woman, its own level
    retention: float  # share of children raised in it who remain as adults

    def __post_init__(self) -> None:
        if not 0.0 < self.share < 1.0:
            raise ParameterError(f"{self.key}: share must be between zero and one")
        if self.fertility <= 0:
            raise ParameterError(f"{self.key}: fertility must be positive")
        if not 0.0 <= self.retention <= 1.0:
            raise ParameterError(f"{self.key}: retention must be a probability")


@dataclass(frozen=True)
class TypeSystem:
    """The types a country's population is divided into, and how they descend.

    `propensity` multiplies the country's own base-year fertility, and is
    normalised so the base-year composition reproduces it exactly. That
    normalisation is an anchor to the present, not a fit to the future: it
    guarantees that with selection switched off this model reproduces the
    ordinary projection, which is the first thing the tests check.
    """

    labels: tuple[str, ...]
    propensity: np.ndarray  # (K,)
    share: np.ndarray  # (K,) base-year shares
    transition: np.ndarray  # (K, K) rows parent, columns child
    group_index: int | None  # which type is the named group, if any
    notes: str

    def __post_init__(self) -> None:
        k = len(self.labels)
        for name, arr, shape in (
            ("propensity", self.propensity, (k,)),
            ("share", self.share, (k,)),
            ("transition", self.transition, (k, k)),
        ):
            if np.asarray(arr).shape != shape:
                raise ParameterError(f"{name} must have shape {shape}")
        if abs(self.share.sum() - 1.0) > 1e-9:
            raise ParameterError("type shares must sum to one")
        if np.any(self.propensity <= 0):
            raise ParameterError("every fertility propensity must be positive")
        rows = self.transition.sum(axis=1)
        if np.any(np.abs(rows - 1.0) > 1e-9):
            raise ParameterError("every transition row must sum to one")
        if np.any(self.transition < 0):
            raise ParameterError("transition probabilities cannot be negative")
        mean = float(self.share @ self.propensity)
        if abs(mean - 1.0) > 1e-9:
            raise ParameterError(
                f"the base-year composition implies {mean:.6f} times the "
                f"country's own fertility; it must be exactly one or the model "
                f"does not start where the data does"
            )

    @property
    def n_types(self) -> int:
        return len(self.labels)

    def mean_propensity(self, shares: np.ndarray) -> np.ndarray:
        """Population-average propensity for any composition. The output."""
        return np.asarray(shares) @ self.propensity


def build(
    parameters: ParameterSet,
    *,
    group: NamedGroup | None = None,
    country_fertility: float | None = None,
    selection_on: bool = True,
) -> TypeSystem:
    """Assemble one country's type system.

    Args:
        parameters: the committed table.
        group: a named group for this country, if one is modelled.
        country_fertility: the country's own base-year total fertility, needed
            to turn the group's absolute fertility into a propensity.
        selection_on: when false, every type has propensity one. The
            composition still moves, but it cannot change fertility, which is
            what "selection off" means in spec section 8's Axis B.
    """
    n_main = int(parameters.value("mainstream_types"))
    cv = parameters.value("mainstream_propensity_cv")
    persistence = parameters.value("mainstream_persistence")

    main_propensity = propensity_bins(n_main, cv) if selection_on else np.ones(n_main)
    main_share = np.full(n_main, 1.0 / n_main)

    if group is None:
        transition = mainstream_transition(n_main, persistence, main_share)
        return TypeSystem(
            labels=MAINSTREAM_LABELS[:n_main] if n_main == 3
            else tuple(f"mainstream-{i}" for i in range(n_main)),
            propensity=main_propensity,
            share=main_share,
            transition=transition,
            group_index=None,
            notes="mainstream only; no named group modelled for this country",
        )

    if country_fertility is None or country_fertility <= 0:
        raise ParameterError(
            "a named group needs the country's own base-year fertility to be "
            "expressed as a propensity"
        )

    group_propensity = group.fertility / country_fertility if selection_on else 1.0
    remaining = 1.0 - group.share
    carried = group.share * group_propensity
    if carried >= 1.0:
        raise ParameterError(
            f"{group.key}: the group alone accounts for {carried:.2f} times the "
            f"country's total fertility, which leaves nothing for everyone else"
        )
    # The mainstream is scaled so the base year still reproduces the country's
    # own fertility exactly, with the group's excess taken off the top.
    main_mean = (1.0 - carried) / remaining
    main_propensity = main_propensity * main_mean if selection_on else main_propensity

    k = n_main + 1
    labels = tuple(MAINSTREAM_LABELS[:n_main]) + (group.label,)
    propensity = np.concatenate([main_propensity, [group_propensity]])
    share = np.concatenate([main_share * remaining, [group.share]])

    transition = np.zeros((k, k))
    transition[:n_main, :n_main] = mainstream_transition(n_main, persistence, main_share)

    leaving = 1.0 - group.retention
    weight = parameters.value("defector_high_propensity_weight")
    destination = np.zeros(n_main)
    destination[-1] = weight  # the highest mainstream propensity
    destination += (1.0 - weight) * main_share
    transition[n_main, :n_main] = leaving * destination
    transition[n_main, n_main] = group.retention

    return TypeSystem(
        labels=labels,
        propensity=propensity,
        share=share,
        transition=transition,
        group_index=n_main,
        notes=(
            f"{group.label} at {group.share:.1%} of {group.iso3}, fertility "
            f"{group.fertility:g} against the country's {country_fertility:.2f}, "
            f"retention {group.retention:.0%}; leavers land in the mainstream "
            f"with {weight:.0%} weight on its high-propensity type"
        ),
    )


def named_groups(parameters: ParameterSet) -> dict[str, NamedGroup]:
    """The named groups the parameter table actually supports.

    Two, and only two, because these are the populations with enough published
    demography to pin retention and fertility separately. Inventing a third
    would be exactly the epicycle spec section 6.10 warns about.
    """
    return {
        "ISR": NamedGroup(
            key="haredi",
            label="haredi",
            iso3="ISR",
            share=parameters.value("group_share_haredi"),
            fertility=parameters.value("group_fertility_haredi"),
            retention=parameters.value("group_retention_haredi"),
        ),
        "USA": NamedGroup(
            key="amish",
            label="amish",
            iso3="USA",
            share=parameters.value("group_share_amish"),
            fertility=parameters.value("group_fertility_amish"),
            retention=parameters.value("group_retention_amish"),
        ),
    }


def toy_demonstration(
    *,
    start_share: float = 0.01,
    group_fertility: float = 6.0,
    mainstream_fertility: float = 1.4,
    retention: float = 0.90,
    generations: int = 4,
) -> list[float]:
    """Spec section 6.6's toy, run rather than asserted.

    A group at one per cent of the population, six children per woman, ninety
    per cent retention, against a mainstream at 1.4. The point is not the
    number: it is that retention is as load-bearing as fertility. A community
    with lower fertility and very high retention outgrows a community with
    higher fertility whose children mostly leave.

    Returns the group's share after each generation. This is a demonstration of
    compounding, **not a forecast** -- the assumptions would change long before
    the arithmetic finished.
    """
    if not 0.0 < start_share < 1.0:
        raise ValueError("the starting share must be between zero and one")
    group, main = start_share, 1.0 - start_share
    shares = []
    for _ in range(generations):
        # Daughters per woman is half of total fertility; leavers join the
        # mainstream rather than disappearing.
        group_daughters = group * group_fertility / 2.0
        main_daughters = main * mainstream_fertility / 2.0
        group, main = (
            group_daughters * retention,
            main_daughters + group_daughters * (1.0 - retention),
        )
        shares.append(group / (group + main))
    return shares

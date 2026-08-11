"""Turning a declared scenario into a run.

`popmodel/scenarios.py` holds the paperwork: what each scenario claims, what
would falsify it, and when that evidence arrives. This holds the mechanics: which
Axis A environment and which Axis B selection setting each of those keys means.

They are kept apart on purpose. The paperwork was written before the mechanism
existed and must not be quietly edited to match whatever the model turned out to
do. If a scenario's mechanism and its implementation disagree, that is a finding,
not a merge conflict.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from popmodel import scenarios as declared
from popmodel.engine import cohort
from popmodel.ingest.wpp import Bundle
from popmodel.mech import composition, engine, environment
from popmodel.mech.parameters import ParameterError, ParameterSet

SELECTION = ("off", "mainstream", "full")

SELECTION_DESCRIPTIONS = {
    "off": (
        "population composition does not feed back into fertility; this "
        "reproduces the logic of conventional projections"
    ),
    "mainstream": (
        "high- and low-fertility tendencies persist imperfectly within the "
        "ordinary population, with no named groups"
    ),
    "full": (
        "mainstream persistence plus named high-fertility groups with their own "
        "retention and defection"
    ),
}


@dataclass(frozen=True)
class MechScenario:
    """One cell of spec section 8's two-axis grid."""

    key: str
    environment: str
    selection: str
    group_convergence: bool = False
    transmission: str = "population"

    def __post_init__(self) -> None:
        if self.environment not in environment.SETTINGS:
            raise ParameterError(f"{self.key}: unknown environment {self.environment!r}")
        if self.selection not in SELECTION:
            raise ParameterError(f"{self.key}: unknown selection {self.selection!r}")
        if self.transmission not in composition.TRANSMISSION_MODES:
            raise ParameterError(
                f"{self.key}: unknown transmission {self.transmission!r}"
            )

    @property
    def declared(self):
        """The paperwork, if this key is one of the spec's named scenarios."""
        return declared.REGISTRY.get(self.key)

    def describe(self) -> str:
        return (
            f"{self.key}: environment = {environment.DESCRIPTIONS[self.environment]}; "
            f"selection = {SELECTION_DESCRIPTIONS[self.selection]}"
        )


#: The named presets of spec section 8, plus the two neutral corners that make
#: the others readable. Keys that exist in `scenarios.py` keep their name so the
#: declared mechanism and falsifiable implication travel with the result.
GRID: dict[str, MechScenario] = {
    "un-equivalent": MechScenario("un-equivalent", "mean-reversion", "off"),
    "development-pressure": MechScenario(
        "development-pressure", "continued-pressure", "off"
    ),
    "selection-rebound": MechScenario("selection-rebound", "stable-low", "full"),
    "race": MechScenario("race", "continued-pressure", "full"),
    "stable-low": MechScenario("stable-low", "stable-low", "mainstream"),
    "gender-equity-rebound": MechScenario(
        "gender-equity-rebound", "mean-reversion", "off"
    ),
    "mainstream-only": MechScenario("mainstream-only", "mean-reversion", "mainstream"),
    "full-selection-un-environment": MechScenario(
        "full-selection-un-environment", "mean-reversion", "full"
    ),
    "race-with-convergence": MechScenario(
        "race", "continued-pressure", "full", group_convergence=True
    ),
    # The same cell with the other transmission rule, so the structural choice
    # is visible as a number rather than argued about in a docstring.
    "race-anchored-culture": MechScenario(
        "race", "continued-pressure", "full", transmission="anchored"
    ),
}

#: Two presets share the mean-reversion path and switched-off selection, and the
#: model cannot tell them apart. That is worth saying rather than hiding behind
#: two identical lines on a chart: the gender-equity story and the UN's own
#: projection make the same numerical claim here and differ only in why. Spec
#: section 7.3 records that the gender-equity mechanism already failed its own
#: best test, so it is kept, labelled, and left to lose on the record.
INDISTINGUISHABLE = {
    "gender-equity-rebound": "un-equivalent",
}


def build_types(
    parameters: ParameterSet,
    *,
    selection: str,
    locations: tuple[str, ...],
    base_tfr: np.ndarray,
    transmission: str = "population",
) -> tuple[tuple[str, ...], np.ndarray, np.ndarray, object, dict[str, str]]:
    """Type labels, propensities, base shares and transitions for every country.

    Returns arrays shaped (L, K) and (L, K, K). Countries without a named group
    still carry the group column; it is simply empty for them, so every country
    has the same type axis and the arrays stay rectangular.
    """
    groups = composition.named_groups(parameters) if selection == "full" else {}
    selection_on = selection != "off"

    systems = {}
    for index, iso3 in enumerate(locations):
        systems[iso3] = composition.build(
            parameters,
            group=groups.get(iso3),
            country_fertility=float(base_tfr[index]),
            selection_on=selection_on,
        )

    n_main = int(parameters.value("mainstream_types"))
    has_group = bool(groups)
    n_types = n_main + (1 if has_group else 0)
    labels = composition.MAINSTREAM_LABELS[:n_main] + (
        ("named-group",) if has_group else ()
    )

    n_loc = len(locations)
    propensity = np.ones((n_loc, n_types))
    share = np.zeros((n_loc, n_types))
    transition = np.zeros((n_loc, n_types, n_types))
    notes = {}

    for index, iso3 in enumerate(locations):
        system = systems[iso3]
        k = system.n_types
        propensity[index, :k] = system.propensity
        share[index, :k] = system.share
        transition[index, :k, :k] = system.transition
        if k < n_types:
            # No named group here. The empty column has to be a valid, absorbing
            # state or the transition rows stop summing to one.
            propensity[index, k:] = 1.0
            transition[index, k:, k:] = np.eye(n_types - k)
        notes[iso3] = system.notes

    rule = composition.TransitionRule(
        persistence=parameters.value("mainstream_persistence"),
        base_share=share,
        mainstream=np.array(
            [not label.startswith("named-group") for label in labels]
        ),
        fixed_rows=transition,
        mode=transmission,
    )
    return labels, propensity, share, rule, notes


def converging_propensity(
    propensity: np.ndarray,
    share: np.ndarray,
    *,
    years: np.ndarray,
    rate_per_generation: float,
    generation_years: float = 30.0,
) -> np.ndarray:
    """A named group's advantage decaying as it stops being unusual.

    Spec section 6.7: taking a small group's present fertility and retention and
    extrapolating them unchanged after it becomes a third of society is the most
    dangerous thing this model could do. The convergence scenario lets the
    group's propensity decay toward the mainstream average instead.

    Returns (T, L, K).
    """
    propensity = np.asarray(propensity, dtype=np.float64)
    n_years = len(years)
    out = np.repeat(propensity[None, :, :], n_years, axis=0)
    if rate_per_generation <= 0:
        return out

    mainstream_mean = (share[:, :-1] * propensity[:, :-1]).sum(axis=1) / np.maximum(
        share[:, :-1].sum(axis=1), 1e-12
    )
    generations = (years - years[0]) / generation_years
    keep = (1.0 - rate_per_generation) ** generations  # (T,)
    group = propensity[:, -1]
    out[:, :, -1] = (
        mainstream_mean[None, :] + (group - mainstream_mean)[None, :] * keep[:, None]
    )
    return out


def initial_population(pop_base: np.ndarray, share: np.ndarray) -> np.ndarray:
    """Split the base population across types.

    Every type gets the country's own age structure, because nobody publishes
    one by type. For the named groups that is conservative in a specific
    direction: a population with six children per woman is far younger than its
    host, so giving it the host's age structure understates how fast it grows.
    Whatever these runs say about group share is a lower bound.
    """
    pop_base = np.asarray(pop_base, dtype=np.float64)
    share = np.asarray(share, dtype=np.float64)
    if pop_base.shape[0] != share.shape[0]:
        raise ParameterError("base population and shares disagree about countries")
    return pop_base[:, None, :, :] * share[:, :, None, None]


def run(
    scenario: MechScenario,
    *,
    bundle: Bundle,
    parameters: ParameterSet,
    reference_tfr: np.ndarray,
    asfr: np.ndarray,
    sx: np.ndarray,
    srb: np.ndarray,
    migration: np.ndarray | None,
    years: np.ndarray,
    end_year: int,
) -> tuple[engine.MechResult, dict]:
    """Run one cell of the grid and return the result plus its provenance."""
    locations = tuple(bundle.iso3)
    base_tfr = asfr[0].sum(axis=1)

    labels, propensity, share, transition, notes = build_types(
        parameters,
        selection=scenario.selection,
        locations=locations,
        base_tfr=base_tfr,
        transmission=scenario.transmission,
    )
    env = environment.build(
        scenario.environment,
        years=years,
        locations=locations,
        reference_tfr=reference_tfr,
        parameters=parameters,
    )

    n_years = end_year - int(years[0])
    projected_years = np.arange(int(years[0]), int(years[0]) + n_years)
    if scenario.group_convergence and scenario.selection == "full":
        rate = parameters.value("group_convergence_per_generation")
        propensity_arg = converging_propensity(
            propensity, share, years=projected_years, rate_per_generation=rate
        )
    else:
        propensity_arg = propensity

    result = engine.project(
        initial_population(bundle.pop_base, share),
        start_year=int(years[0]),
        sx=sx,
        asfr=asfr,
        srb=srb,
        propensity=propensity_arg,
        transition=transition,
        environment=env.multiplier,
        labels=labels,
        locations=locations,
        migration=migration,
        n_years=n_years,
    )

    paperwork = scenario.declared
    provenance = {
        "key": scenario.key,
        "environment": scenario.environment,
        "selection": scenario.selection,
        "group_convergence": scenario.group_convergence,
        "transmission": scenario.transmission,
        "description": scenario.describe(),
        "environment_summary": env.summary(),
        "environment_knobs": list(env.knobs),
        "named_group_notes": {
            iso3: note for iso3, note in notes.items() if "named" not in note
        },
        "mechanism": paperwork.mechanism if paperwork else "",
        "falsifiable_implication": paperwork.falsifiable_implication if paperwork else "",
        "resolution_date": paperwork.resolution_date if paperwork else "",
        "declared_axis_a": paperwork.axis_a if paperwork else "",
        "declared_axis_b": paperwork.axis_b if paperwork else "",
        "indistinguishable_from": INDISTINGUISHABLE.get(scenario.key),
    }
    return result, provenance

"""Named scenarios, and the rules for what may call itself one.

Spec section 8: "Every substantive scenario must ship with a named mechanism,
parameter sources, a falsifiable implication, and a resolution date." That is
enforced here structurally - the dataclass will not construct without those
fields - rather than left to good intentions.

Most of the scenarios in spec section 8 need the Bayesian layer (phase 4) and
the mechanistic layer (phase 5) before they mean anything. They are declared
below anyway, flagged as not implemented, because a list of what is missing is
more useful than silence about it. Asking for an unimplemented scenario raises.

What IS implemented at phase 2 involves no theory about future fertility at
all. Each just hands the engine a different set of published rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from popmodel.engine import cohort
from popmodel.ingest.wpp import Bundle

# Rates beyond the last WPP year (2100) have to come from somewhere. The engine
# holds the final supplied year constant. For mortality that means life
# expectancy stops improving in 2100, which is very probably wrong - the
# recurring institutional failure in spec section 10 is that mortality gains get
# under-projected, decade after decade. Frozen mortality is a floor on
# longevity, not a neutral choice, and it makes the 2150 population totals
# slightly conservative.
POST_WPP_MORTALITY = "held at the 2100 level; see POST_WPP_MORTALITY in scenarios.py"


@dataclass(frozen=True)
class Scenario:
    """One named future, with the paperwork that makes it checkable."""

    key: str
    title: str
    mechanism: str  # what is claimed to be doing the work
    parameter_sources: str  # where the numbers came from
    falsifiable_implication: str  # what would show this wrong
    resolution_date: str  # when that evidence arrives
    axis_a: str  # fertility environment, spec section 8
    axis_b: str  # selection and transmission, spec section 8
    implemented: bool = False
    delivered_by: str = ""  # which build phase will implement it
    scenario_knobs: list[str] = field(default_factory=list)  # spec 6.10

    def rates(self, bundle: Bundle, n_years: int) -> dict[str, np.ndarray]:
        raise NotImplementedError(
            f"Scenario {self.key!r} is declared but not implemented "
            f"({self.delivered_by or 'no phase assigned'})."
        )


@dataclass(frozen=True)
class RateScenario(Scenario):
    """A scenario that is fully specified by published rate series."""

    fertility_rule: str = "medium"  # "medium" or "constant"
    use_migration: bool = False

    def rates(self, bundle: Bundle, n_years: int) -> dict[str, np.ndarray]:
        if self.fertility_rule == "medium":
            asfr = bundle.asfr
        elif self.fertility_rule == "constant":
            # The UN's own frozen rates, not our 2024 ones - they froze 2023,
            # which is about 0.6% higher. Using theirs makes the comparison
            # against their published variant a test rather than a coincidence.
            # The engine holds the last year of a short series constant, so one
            # year is all that is needed.
            asfr = bundle.asfr_constant[None, ...]
        else:
            raise ValueError(f"unknown fertility rule {self.fertility_rule!r}")
        return {"sx": bundle.sx, "asfr": asfr, "srb": bundle.srb}


REGISTRY: dict[str, Scenario] = {}


def register(s: Scenario) -> Scenario:
    if s.key in REGISTRY:
        raise ValueError(f"scenario {s.key!r} is already registered")
    REGISTRY[s.key] = s
    return s


def get(key: str) -> Scenario:
    if key not in REGISTRY:
        raise KeyError(f"no scenario {key!r}. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def implemented() -> list[Scenario]:
    return [s for s in REGISTRY.values() if s.implemented]


# ---------------------------------------------------------------------------
# Implemented at phase 2. No theory about future fertility in any of them.
# ---------------------------------------------------------------------------

register(
    RateScenario(
        key="un-medium-no-migration",
        title="UN medium fertility and mortality, migration switched off",
        mechanism=(
            "None of the project's own. The UN's Phase III model supplies "
            "fertility; this run exists to prove the arithmetic, not to make a "
            "claim about the world."
        ),
        parameter_sources="WPP 2024 medium variant, unmodified",
        falsifiable_implication=(
            "Must land on the UN's published zero-migration variant to 2100. "
            "If it does not, every other result in the repo is suspect."
        ),
        resolution_date="already resolved; see out/validation_wpp2024.json",
        axis_a="mean reversion (inherited from the UN, not endorsed)",
        axis_b="off",
        implemented=True,
        fertility_rule="medium",
        use_migration=False,
    )
)

register(
    RateScenario(
        key="un-medium",
        title="UN medium variant, with migration backed out of the UN's own path",
        mechanism="As above. Migration is a residual, not an estimate.",
        parameter_sources=(
            "WPP 2024 medium variant; net migrants by age derived by residual "
            "because the UN does not publish them by single year of age"
        ),
        falsifiable_implication=(
            "None worth the name. The migration term is fitted to the series it "
            "is compared against, so agreement is close to guaranteed. Reported "
            "as a diagnostic only."
        ),
        resolution_date="n/a - not a prediction",
        axis_a="mean reversion (inherited)",
        axis_b="off",
        implemented=True,
        fertility_rule="medium",
        use_migration=True,
        scenario_knobs=["net migration by age (residual, not independently sourced)"],
    )
)

register(
    RateScenario(
        key="constant-fertility",
        title="Constant fertility: 2024 rates held forever",
        mechanism=(
            "Deliberately none. Every woman in 2150 is assumed to bear children "
            "at exactly the 2024 rate for her age and country. This is not a "
            "forecast and nobody believes it."
        ),
        parameter_sources="WPP 2024 age-specific fertility for 2024, frozen",
        falsifiable_implication=(
            "Absurdity check and engine test in one: it must reproduce the UN's "
            "own published constant-fertility variant to 2100. Spec section 8 "
            "also expects roughly 244 billion at 2150 - see the note in "
            "scripts/run_to_2150.py for why that figure does not transfer to "
            "the 2024 revision."
        ),
        resolution_date="n/a - a check, not a claim",
        axis_a="none (fertility environment frozen)",
        axis_b="off",
        implemented=True,
        fertility_rule="constant",
        use_migration=True,
    )
)


# ---------------------------------------------------------------------------
# Declared, not implemented. Spec section 8's two-axis system. These need the
# Bayesian layer and the mechanistic layer to exist first.
# ---------------------------------------------------------------------------


def _todo(key, title, mechanism, axis_a, axis_b, implication, resolves, phase, knobs=()):
    register(
        Scenario(
            key=key,
            title=title,
            mechanism=mechanism,
            parameter_sources="not yet pinned - see spec section 6.10",
            falsifiable_implication=implication,
            resolution_date=resolves,
            axis_a=axis_a,
            axis_b=axis_b,
            implemented=False,
            delivered_by=phase,
            scenario_knobs=list(knobs),
        )
    )


_todo(
    "development-pressure",
    "Development-pressure baseline",
    "The opportunity cost of parenthood keeps rising, so a woman with a given "
    "fertility propensity bears fewer children in each successive cohort. No "
    "evolutionary feedback.",
    "continued development pressure",
    "off",
    "Completed cohort fertility for the early-1990s birth cohorts lands near "
    "1.1 in Korea and Spain rather than 1.3-1.4.",
    "~2038",
    "phase 5",
    ["rate of decline in the propensity-to-birth mapping"],
)
_todo(
    "selection-rebound",
    "Selection rebound",
    "Higher-fertility dispositions and group memberships are transmitted to "
    "children well enough that population composition shifts toward them faster "
    "than the fertility environment moves down.",
    "stable low fertility",
    "full transmission model",
    "A measurable rise in completed cohort fertility, and a rising share of "
    "high-fertility lineages, in populations where transmission can be observed.",
    "~2038 first read; successive cohorts after",
    "phase 5",
    ["group retention", "intermarriage and assimilation rates at larger group scale"],
)
_todo(
    "race",
    "Race between development and selection",
    "Both at once. Composition shifts toward higher-fertility types while the "
    "environment makes every type bear fewer children. The output of interest "
    "is whether and when selection overtakes the environmental shift.",
    "continued development pressure",
    "full transmission model",
    "Predicts a specific decade in which composition change starts to dominate. "
    "Wrong decade, wrong model.",
    "successive cohorts from ~2038",
    "phase 5",
    ["as above, plus how fast group parameters change with group size"],
)
_todo(
    "stable-low",
    "Stable-low equilibrium",
    "Development pressure weakens and selection is present, and the two roughly "
    "cancel at a persistently low fertility level.",
    "stable low fertility",
    "mainstream persistence only",
    "Completed cohort fertility flattens rather than continuing to fall, without "
    "a rebound.",
    "~2038 onward",
    "phase 5",
)
_todo(
    "gender-equity-rebound",
    "Gender-equity rebound",
    "Fertility recovers once institutional gender equity catches up with "
    "individual-level equity (McDonald). Included despite already failing its "
    "own best test in the Nordics - spec section 7.3 - so that it loses on the "
    "record rather than by omission.",
    "mean reversion",
    "off",
    "Nordic completed cohort fertility recovers toward 1.9. Present evidence "
    "runs the other way.",
    "evidence already in; tracked anyway",
    "phase 4",
)

del _todo

"""How many children a person of a given propensity actually has.

Spec section 6.9. The other half of the competition: `composition.py` decides
who is becoming more common, and this decides what any given disposition
produces. Selection can make high-fertility dispositions more common while
observed fertility still falls, because the environment is moving underneath
them.

The environment is expressed as a multiplier on the UN's own fertility path,
equal to one in every year of that path. So the "mean reversion" setting is not
a model of anything: it is the UN's projection, unmodified, and it is the
reference the other two are departures from. That keeps the comparison honest.
Any difference in output is attributable to a stated change, not to a different
implementation.

The three settings are spec section 8's Axis A:

* **mean reversion** -- the UN's own path, which pulls post-transition fertility
  back toward a stable long-run level.
* **stable low** -- the downward shift eventually stops, but there is no
  rebound. Implemented as the running minimum of the UN's path, which removes
  the recovery while keeping everything the UN says about the way down.
* **continued development pressure** -- the opportunity cost of parenthood
  keeps rising, so a person of fixed propensity has fewer children in each
  later cohort. A stated proportional decline per decade, with a floor.

The decline rate is a scenario knob and the most important number in the model.
It is not fitted, cannot be looked up, and is the thing the project is trying
to learn. Spec section 6.9 is explicit that this must be a small number of
transparent paths rather than a speculative economic forecast.

What this deliberately does not do
----------------------------------
It does not model GDP. Spec section 6.9 calls GDP an upstream summary rather
than the mechanism, and warns against a disguised assumption that higher income
always means lower fertility. What is modelled is the direction and pace of the
environment, with the mechanism named in prose and the magnitude left as an
explicit dial.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from popmodel.mech.parameters import ParameterError, ParameterSet

SETTINGS = ("mean-reversion", "stable-low", "continued-pressure")

DESCRIPTIONS = {
    "mean-reversion": (
        "the UN's own fertility path, unmodified; post-transition fertility is "
        "pulled back toward a stable long-run level"
    ),
    "stable-low": (
        "the downward environmental shift stops but does not reverse; the UN's "
        "path is followed down and its rebound removed"
    ),
    "continued-pressure": (
        "the opportunity cost of parenthood keeps rising, so a person of fixed "
        "propensity has fewer children in each later cohort"
    ),
}


@dataclass(frozen=True)
class Environment:
    """A multiplier on the UN's fertility path, by year and country."""

    setting: str
    years: np.ndarray  # (T,)
    locations: tuple[str, ...]
    multiplier: np.ndarray  # (T, L)
    description: str
    knobs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.setting not in SETTINGS:
            raise ParameterError(f"unknown environment setting {self.setting!r}")
        if self.multiplier.shape != (len(self.years), len(self.locations)):
            raise ParameterError("environment multiplier has the wrong shape")
        if np.any(self.multiplier <= 0) or not np.all(np.isfinite(self.multiplier)):
            raise ParameterError("environment multipliers must be finite and positive")

    def summary(self) -> str:
        final = self.multiplier[-1]
        return (
            f"{self.setting}: {self.description}. By {int(self.years[-1])} the "
            f"environment sits at {final.mean():.2f} times the UN's own path on "
            f"average ({final.min():.2f} to {final.max():.2f} across countries)"
        )


def build(
    setting: str,
    *,
    years: np.ndarray,
    locations: tuple[str, ...],
    reference_tfr: np.ndarray,
    parameters: ParameterSet,
    pressure_from: int = 2050,
) -> Environment:
    """Construct one Axis A path.

    Args:
        reference_tfr: (T, L) the UN's own total fertility by year and country.
            Used only to work out where its rebound is, never fitted to.
        pressure_from: the year continued development pressure starts to bite.
            Before it, the environment follows the stable-low path, because a
            pressure that had been operating all along would already be visible
            in the UN's own estimates.
    """
    years = np.asarray(years, dtype=np.int64)
    reference_tfr = np.asarray(reference_tfr, dtype=np.float64)
    if reference_tfr.shape != (len(years), len(locations)):
        raise ParameterError("reference fertility has the wrong shape")
    if np.any(reference_tfr <= 0):
        raise ParameterError("reference fertility must be positive everywhere")

    if setting == "mean-reversion":
        multiplier = np.ones_like(reference_tfr)
        knobs: tuple[str, ...] = ()
    else:
        # The running minimum removes any recovery while keeping the descent.
        floor_path = np.minimum.accumulate(reference_tfr, axis=0)
        multiplier = floor_path / reference_tfr
        knobs = ()
        if setting == "continued-pressure":
            rate = parameters.value("development_decline_per_decade")
            floor = parameters.value("development_floor")
            if not 0.0 <= rate < 1.0:
                raise ParameterError("the decline per decade must be in [0, 1)")
            decades = np.maximum(years - pressure_from, 0) / 10.0
            decay = (1.0 - rate) ** decades
            multiplier = multiplier * decay[:, None]
            multiplier = np.maximum(multiplier, floor)
            knobs = ("development_decline_per_decade", "development_floor")

    return Environment(
        setting=setting,
        years=years,
        locations=tuple(locations),
        multiplier=multiplier,
        description=DESCRIPTIONS[setting],
        knobs=knobs,
    )

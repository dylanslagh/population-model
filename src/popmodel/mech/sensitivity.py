"""Small, explicit calculations for the selection/pressure break-even test.

The benchmark is the stable-low environment: the observed and already-underway
fertility decline is retained, but no further post-2050 environmental decline
is asserted.  Selection is then allowed to change population composition.

An *additional* development-pressure rate is a stress test applied on top of
that benchmark.  It is deliberately not an economic forecast.  The break-even
rate says how large that extra decline would need to be to cancel a measured
selection multiplier at a stated horizon.
"""

from __future__ import annotations

import numpy as np


def pressure_multiplier(rate_per_decade, decades):
    """Remaining fertility-environment multiplier after proportional decline."""
    rate = np.asarray(rate_per_decade, dtype=np.float64)
    span = np.asarray(decades, dtype=np.float64)
    if np.any((rate < 0.0) | (rate >= 1.0)):
        raise ValueError("the decline per decade must be in [0, 1)")
    if np.any(span < 0.0):
        raise ValueError("decades cannot be negative")
    return (1.0 - rate) ** span


def net_fertility_multiplier(selection_effect, rate_per_decade, decades):
    """Selection times the additional environmental stress test."""
    effect = np.asarray(selection_effect, dtype=np.float64)
    if np.any(effect <= 0.0):
        raise ValueError("selection effects must be positive")
    return effect * pressure_multiplier(rate_per_decade, decades)


def break_even_rate(selection_effect, decades):
    """Per-decade decline that makes the net fertility multiplier equal one.

    A negative result means selection is already lowering fertility, so a
    positive development-pressure rate is not needed to reach parity.
    """
    effect = np.asarray(selection_effect, dtype=np.float64)
    span = np.asarray(decades, dtype=np.float64)
    if np.any(effect <= 0.0):
        raise ValueError("selection effects must be positive")
    if np.any(span <= 0.0):
        raise ValueError("break-even requires a positive number of decades")
    return 1.0 - effect ** (-1.0 / span)


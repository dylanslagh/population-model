"""Proper scoring rules.

Spec section 9: predictions get scored with a proper scoring rule - log score
or CRPS. "Proper" is a technical word with a plain meaning: the rule is
designed so that the best score you can expect comes from stating what you
actually believe. You cannot improve your expected score by hedging, by
claiming more certainty than you have, or by claiming less.

Two are implemented, and no others, because two is enough and every dependency
and every line is a maintenance liability on a project meant to outlive its
author's interest in it.

    CRPS      for a full predictive distribution against a single observed
              number. In the same units as the thing predicted, which makes it
              readable: a CRPS of 0.05 children per woman means something.
    Pinball   quantile loss, for when only a few quantiles were stored rather
              than samples. Averaged over quantiles it approximates CRPS.

Both are oriented so that LOWER IS BETTER.
"""

from __future__ import annotations

import numpy as np


def crps_from_samples(samples: np.ndarray, observation: float) -> float:
    """Continuous ranked probability score, estimated from posterior draws.

    Uses the energy form:

        CRPS = mean|X - y|  -  0.5 * mean|X - X'|

    where X and X' are independent draws from the predictive distribution and y
    is what happened. The first term punishes being far from the truth; the
    second rewards a distribution that is not needlessly wide. A point
    prediction has a zero second term, so it can only win by being nearly
    right - which is the property that makes the rule proper.

    Exact for the estimator, not merely asymptotic, but it costs O(n^2). For
    the sample sizes this project will store (thousands, not millions) that is
    irrelevant and the clarity is worth more than the speed.
    """
    x = np.asarray(samples, dtype=float).ravel()
    if x.size == 0:
        raise ValueError("no samples")
    if not np.all(np.isfinite(x)):
        raise ValueError("samples contain non-finite values")
    if not np.isfinite(observation):
        raise ValueError("observation is not finite")

    term1 = np.abs(x - observation).mean()
    # Sorting turns the pairwise term into a linear-time weighted sum, which
    # keeps this usable if a future model stores a lot of draws.
    xs = np.sort(x)
    n = xs.size
    weights = 2.0 * np.arange(1, n + 1) - n - 1.0
    term2 = 2.0 * float(np.dot(weights, xs)) / (n * n)
    return float(term1 - 0.5 * term2)


def crps_normal(mean: float, sd: float, observation: float) -> float:
    """CRPS of a normal predictive distribution, in closed form.

    Here because it has an exact answer, which makes it the reference the
    sample-based estimator above is tested against. A scoring rule that is
    itself wrong would corrupt the entire track record silently, and the track
    record is the part of this project that is supposed to still be worth
    something in fifty years.
    """
    from math import erf, exp, pi, sqrt

    if sd <= 0:
        raise ValueError("sd must be positive")
    z = (observation - mean) / sd
    cdf = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    pdf = exp(-0.5 * z * z) / sqrt(2.0 * pi)
    return float(sd * (z * (2.0 * cdf - 1.0) + 2.0 * pdf - 1.0 / sqrt(pi)))


def pinball_loss(quantiles: dict[float, float], observation: float) -> float:
    """Average quantile loss over the stored quantiles. Lower is better.

    For quantile level q and predicted value v, the loss is
    q*(y-v) when the observation is above the prediction and (1-q)*(v-y) when
    it is below. Asymmetric on purpose: missing low on a 5th percentile is a
    different error from missing high on it.
    """
    if not quantiles:
        raise ValueError("no quantiles")
    total = 0.0
    for q, v in quantiles.items():
        if not 0.0 < q < 1.0:
            raise ValueError(f"quantile level {q} is not strictly between 0 and 1")
        diff = observation - v
        total += q * diff if diff >= 0 else (q - 1.0) * diff
    return float(total / len(quantiles))


def interval_coverage(quantiles: dict[float, float], observation: float, lower: float, upper: float) -> bool:
    """Did the observation fall inside a stated interval? Calibration, over many predictions."""
    for level in (lower, upper):
        if level not in quantiles:
            raise KeyError(f"quantile {level} was not stored; have {sorted(quantiles)}")
    return bool(quantiles[lower] <= observation <= quantiles[upper])


def absolute_error(prediction: float, observation: float) -> float:
    """For point predictions. Not a proper scoring rule - there is no
    distribution to be proper about - and recorded as a separate field so it is
    never mistaken for one."""
    return float(abs(prediction - observation))

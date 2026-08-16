"""Continue the published fertility and longevity trajectories past 2100.

The source archive stops at 2100 and this project runs to 2150. Until now the
gap was filled by holding the final rates constant, which is a strong claim
stated as housekeeping: it says fertility stops wandering and longevity stops
improving, both exactly at the boundary, for no reason. This module replaces
that with an emulator of the source's own late-horizon behaviour, in the same
spirit as `migration.py` and with the same limitation: the public archive omits
the fitted MCMC state, so the parameters here are reconstructed from output.

What the source actually does in its last thirty years
-----------------------------------------------------
Fitted over 2070-2100, the two components behave differently, and the
continuation has to respect that rather than apply one rule to both.

**Fertility is stationary within a trajectory.** Each path fluctuates around its
own level with an autocorrelation near 0.85 and a stationary spread near 0.12
children. Meanwhile the spread *between* trajectories at 2100 is about 0.40 --
three times larger. That is the published model's structure: the long-run level
is itself uncertain, and most of the 2150 fertility uncertainty is already
present at the boundary. So each path is continued as an AR(1) around **its own
2100 value**, not around a pooled country mean. Pooling across trajectories
would fit a single level per country and drag every draw toward it, quietly
deleting the posterior spread that is the whole point of having 1,000 draws.

**Longevity is still trending.** The annual gain over 2070-2100 averages 0.116
years and is strikingly uniform across countries (0.100 to 0.154). Freezing it
asserts that improvement halts at the boundary. Each path is therefore continued
as a random walk with that country's own fitted drift, plus AR(1) noise on the
gain. The male series is derived from the female series and a separately
continued sex gap, so the two cannot cross.

What this deliberately does not do
----------------------------------
Fertility is still drifting down slightly at the boundary, by about 0.003
children a year. Centring each path on its 2100 value drops that residual drift
rather than extrapolating it. Extrapolating would subtract roughly 0.15 children
by 2150, which is a real assumption about a fifty-year horizon and not one the
last thirty years of a projection can settle. Dropping it is the conservative
choice in the direction that *raises* the population, and it is stated here so
that the sign of the bias is visible rather than buried.

Nor does this reproduce the published mortality model's deceleration: real
bayesLife gains slow as life expectancy rises, and a constant drift does not.
The continuation therefore runs slightly hot on longevity, which is measured in
the ensemble receipt rather than asserted to be small.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

DEFAULT_FIT_START_YEAR = 2070
DEFAULT_SEED = 20260816

#: How far outside the source's own observed range a continued value may stray
#: before it is clipped. The rails are derived from the archive rather than
#: written down, because guessing them gets this wrong: a first attempt bounded
#: the female-male life-expectancy gap at zero and fifteen years and clipped a
#: tenth of all values, when the source's own gap runs from -6.6 to +20.2. A
#: rail that fires on ordinary source behaviour is not a safety check, it is a
#: silent model.
RAIL_MARGIN = 0.25


class RateContinuationError(RuntimeError):
    """The continuation could not be fitted or produced impossible rates."""


def _ar1_within(paths: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Autocorrelation and innovation spread, fitted inside each trajectory.

    Args:
        paths: (T, L, K) the fit window, by year, country and trajectory.

    Returns:
        (phi, sigma), each (L,), pooled across trajectories *after* removing
        each trajectory's own level. Removing the level first is what keeps
        this a within-path statistic; pooling the levels themselves would
        measure the posterior spread instead and give an autocorrelation near
        one for every country.
    """
    deviation = paths - paths.mean(axis=0, keepdims=True)
    lag, lead = deviation[:-1], deviation[1:]
    numerator = (lag * lead).sum(axis=(0, 2))
    denominator = (lag * lag).sum(axis=(0, 2))
    phi = np.divide(
        numerator, denominator,
        out=np.zeros_like(numerator), where=denominator > 1e-12,
    )
    # An autocorrelation at or above one is a unit root the stationary form
    # cannot represent; clipping is visible in the receipt.
    phi = np.clip(phi, 0.0, 0.98)
    residual = lead - phi[None, :, None] * lag
    sigma = residual.std(axis=(0, 2))
    sigma = np.maximum(sigma, 1e-6)
    return phi, sigma


@dataclass(frozen=True)
class TrajectoryContinuation:
    """Fitted late-horizon behaviour of one archive, and how it was obtained."""

    loc_id: np.ndarray
    tfr_phi: np.ndarray
    tfr_sigma: np.ndarray
    e0_drift: np.ndarray          # mean annual female gain, years
    e0_gain_phi: np.ndarray
    e0_gain_sigma: np.ndarray
    gap_phi: np.ndarray
    gap_sigma: np.ndarray
    fit_start_year: int
    fit_end_year: int
    source: str

    def receipt(self) -> dict:
        return {
            "method": (
                "fertility continued as AR(1) around each trajectory's own 2100 "
                "value; life expectancy continued as a random walk with each "
                "country's fitted drift plus AR(1) noise on the annual gain; "
                "the female-male gap continued as AR(1) around its own 2100 value"
            ),
            "fit_years": [self.fit_start_year, self.fit_end_year],
            "tfr_phi_median": float(np.median(self.tfr_phi)),
            "tfr_sigma_median": float(np.median(self.tfr_sigma)),
            "e0_drift_years_per_year_median": float(np.median(self.e0_drift)),
            "e0_drift_years_per_year_range": [
                float(self.e0_drift.min()), float(self.e0_drift.max())
            ],
            "residual_tfr_drift_dropped": (
                "each path is centred on its own 2100 value, so the small "
                "downward drift still present at the boundary is not "
                "extrapolated; doing so would subtract roughly 0.15 children "
                "by 2150 and would raise, not lower, the reported population"
            ),
            "claim_boundary": (
                "the public archive omits the fitted MCMC state; this is an "
                "emulator of its late-horizon output, not an official "
                "continuation of the published model"
            ),
            "source": self.source,
        }


def fit(
    *,
    years: np.ndarray,
    tfr: np.ndarray,
    e0_female: np.ndarray,
    e0_male: np.ndarray,
    loc_id: np.ndarray,
    fit_start_year: int = DEFAULT_FIT_START_YEAR,
    source: str = "UW WPP 2024-aligned annual trajectories",
) -> TrajectoryContinuation:
    """Fit the late-horizon behaviour of the published trajectories."""
    years = np.asarray(years, dtype=np.int64)
    window = years >= fit_start_year
    if window.sum() < 10:
        raise RateContinuationError(
            f"the fit window from {fit_start_year} holds only {int(window.sum())} "
            f"years; that is too few to estimate an autocorrelation"
        )
    for name, array in (("tfr", tfr), ("e0_female", e0_female), ("e0_male", e0_male)):
        if array.shape[0] != len(years):
            raise RateContinuationError(f"{name} does not cover the same years")
        if not np.all(np.isfinite(array)):
            raise RateContinuationError(f"{name} contains non-finite values")

    tfr_phi, tfr_sigma = _ar1_within(tfr[window])

    gain = np.diff(e0_female[window], axis=0)
    e0_drift = gain.mean(axis=(0, 2))
    gain_phi, gain_sigma = _ar1_within(gain)

    gap = e0_female[window] - e0_male[window]
    gap_phi, gap_sigma = _ar1_within(gap)

    if np.any(e0_drift < 0):
        raise RateContinuationError(
            "a country's late-horizon life expectancy trend is negative; check "
            "the archive before continuing it fifty years"
        )
    return TrajectoryContinuation(
        loc_id=np.asarray(loc_id, dtype=np.int64),
        tfr_phi=tfr_phi, tfr_sigma=tfr_sigma,
        e0_drift=e0_drift, e0_gain_phi=gain_phi, e0_gain_sigma=gain_sigma,
        gap_phi=gap_phi, gap_sigma=gap_sigma,
        fit_start_year=int(fit_start_year), fit_end_year=int(years[-1]),
        source=source,
    )


def extend(
    *,
    years: np.ndarray,
    tfr: np.ndarray,
    e0_female: np.ndarray,
    e0_male: np.ndarray,
    continuation: TrajectoryContinuation,
    end_year: int,
    seed: int = DEFAULT_SEED,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Continue every trajectory to `end_year` inclusive.

    Returns:
        (years, tfr, e0_female, e0_male, diagnostics), each rate array shaped
        (T', L, K) and starting where the source did.
    """
    years = np.asarray(years, dtype=np.int64)
    if end_year <= years[-1]:
        raise RateContinuationError(
            f"end year {end_year} is not beyond the source's {int(years[-1])}"
        )
    extra = np.arange(years[-1] + 1, end_year + 1, dtype=np.int64)
    n_extra = len(extra)
    n_loc, n_draw = tfr.shape[1], tfr.shape[2]
    rng = np.random.default_rng(seed)

    def normal() -> np.ndarray:
        return rng.standard_normal((n_loc, n_draw))

    # Fertility: stationary around each path's own boundary value.
    tfr_level = tfr[-1]
    tfr_out = np.empty((n_extra, n_loc, n_draw))
    state = tfr_level.copy()
    phi, sigma = continuation.tfr_phi[:, None], continuation.tfr_sigma[:, None]
    for step in range(n_extra):
        state = tfr_level + phi * (state - tfr_level) + sigma * normal()
        tfr_out[step] = state

    # Longevity: random walk with the country's own fitted drift.
    e0_out = np.empty((n_extra, n_loc, n_draw))
    gap_out = np.empty((n_extra, n_loc, n_draw))
    level = e0_female[-1].copy()
    gain = np.broadcast_to(continuation.e0_drift[:, None], (n_loc, n_draw)).copy()
    drift = continuation.e0_drift[:, None]
    gain_phi, gain_sigma = continuation.e0_gain_phi[:, None], continuation.e0_gain_sigma[:, None]
    gap_state = (e0_female[-1] - e0_male[-1]).copy()
    gap_level = gap_state.copy()
    gap_phi, gap_sigma = continuation.gap_phi[:, None], continuation.gap_sigma[:, None]
    for step in range(n_extra):
        gain = drift + gain_phi * (gain - drift) + gain_sigma * normal()
        level = level + gain
        e0_out[step] = level
        gap_state = gap_level + gap_phi * (gap_state - gap_level) + gap_sigma * normal()
        gap_out[step] = gap_state

    def rails(observed: np.ndarray, *, positive: bool = False,
              trend: float = 0.0, sigma: float = 0.0) -> tuple[float, float]:
        """Absurdity bounds derived from the archive, not written down.

        Two corrections, both found by a check that fired when it should not
        have. A width-proportional pad drives the floor negative whenever a
        positive quantity has a wide range: fertility spans 0.33 to 7.27, so a
        quarter of that width puts the rail at -1.45 and permits a negative
        birth rate. And for a quantity that is still trending, the source's own
        observed range is guaranteed to bind, because leaving that range is
        precisely what a trend does; the bound must therefore allow the fitted
        trend to carry the series as far as it can over the continued years.

        The pad is also floored at several innovation standard deviations, so
        that a rail can never sit inside the noise the continuation itself
        legitimately generates. Without that, a source series with a nearly
        constant value gets a nearly zero-width rail and clips almost every
        draw.
        """
        low, high = float(observed.min()), float(observed.max())
        pad = max(RAIL_MARGIN * (high - low), 4.0 * sigma, 1e-6)
        floor = low - pad
        if positive:
            floor = max(floor, 0.5 * low)
        return floor, high + pad + max(trend, 0.0) * n_extra

    source_gap = e0_female - e0_male
    stationary = lambda phi, sig: float(  # noqa: E731
        np.max(sig / np.sqrt(np.maximum(1.0 - phi ** 2, 1e-6)))
    )
    tfr_rail = rails(
        tfr, positive=True,
        sigma=stationary(continuation.tfr_phi, continuation.tfr_sigma),
    )
    e0_rail = rails(
        e0_female, positive=True,
        trend=float(continuation.e0_drift.max()),
        sigma=float(continuation.e0_gain_sigma.max()) * np.sqrt(n_extra),
    )
    gap_rail = rails(
        source_gap,
        sigma=stationary(continuation.gap_phi, continuation.gap_sigma),
    )

    clipped = {
        "tfr": int(((tfr_out < tfr_rail[0]) | (tfr_out > tfr_rail[1])).sum()),
        "e0_female": int(((e0_out < e0_rail[0]) | (e0_out > e0_rail[1])).sum()),
        "sex_gap": int(((gap_out < gap_rail[0]) | (gap_out > gap_rail[1])).sum()),
    }
    np.clip(tfr_out, *tfr_rail, out=tfr_out)
    np.clip(e0_out, *e0_rail, out=e0_out)
    np.clip(gap_out, *gap_rail, out=gap_out)
    male_out = e0_out - gap_out
    if np.any(tfr_out <= 0):
        raise RateContinuationError("the fertility continuation produced a non-positive rate")

    generated = n_extra * n_loc * n_draw
    diagnostics = {
        **continuation.receipt(),
        "seed": int(seed),
        "extended_from": int(years[-1]) + 1,
        "extended_to": int(end_year),
        "generated_values": generated,
        "clipped_values": clipped,
        "clipped_share": sum(clipped.values()) / (3 * generated),
        "rails": {
            "derivation": (
                f"the source's own observed range, padded by {RAIL_MARGIN:.0%} "
                f"of its width; a clip means the continuation left the space "
                f"the archive ever occupied"
            ),
            "tfr": list(tfr_rail),
            "e0_female": list(e0_rail),
            "sex_gap": list(gap_rail),
        },
        "world_tfr_median_2100": float(np.median(tfr[-1])),
        "world_tfr_median_final": float(np.median(tfr_out[-1])),
        "world_e0_female_median_2100": float(np.median(e0_female[-1])),
        "world_e0_female_median_final": float(np.median(e0_out[-1])),
    }
    return (
        np.concatenate([years, extra]),
        np.concatenate([tfr, tfr_out]),
        np.concatenate([e0_female, e0_out]),
        np.concatenate([e0_male, male_out]),
        diagnostics,
    )


def extend_bundle(bundle, *, end_year: int, seed: int = DEFAULT_SEED,
                  fit_start_year: int = DEFAULT_FIT_START_YEAR):
    """Return a copy of a draw bundle whose rates reach `end_year`.

    The bundle is otherwise untouched, so every downstream consumer -- the
    schedule converter, the propagator, the vintage writer -- keeps working
    without knowing the later years were emulated rather than published. What
    stops that being a way to lose track of the boundary is the diagnostics
    dictionary, which every caller is expected to write into its receipt.
    """
    continuation = fit(
        years=bundle.years, tfr=bundle.tfr, e0_female=bundle.e0_female,
        e0_male=bundle.e0_male, loc_id=bundle.loc_id,
        fit_start_year=fit_start_year,
    )
    years, tfr, e0_female, e0_male, diagnostics = extend(
        years=bundle.years, tfr=bundle.tfr, e0_female=bundle.e0_female,
        e0_male=bundle.e0_male, continuation=continuation,
        end_year=end_year, seed=seed,
    )
    return replace(
        bundle, years=years, tfr=tfr, e0_female=e0_female, e0_male=e0_male,
    ), diagnostics

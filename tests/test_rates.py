"""The post-2100 fertility and longevity continuation behaves as advertised.

The trap this module exists to avoid is subtle enough to deserve a test of its
own: fitting the autoregression across trajectories rather than within them
would estimate the posterior spread instead of the within-path dynamics, return
an autocorrelation near one, and then pull every draw toward a single country
mean -- deleting the ensemble spread while producing perfectly plausible-looking
output. `test_between_draw_spread_survives` is the check that would catch it.
"""

from __future__ import annotations

import numpy as np
import pytest

from popmodel import rates


def synthetic(n_years=40, n_loc=3, n_draw=200, seed=7):
    """Paths that are stationary within a trajectory and dispersed between them.

    Each trajectory gets its own level, drawn wide, and then wanders around that
    level with a known autocorrelation. This is the structure the published
    archive actually has, so a fitter that confuses the two is visible here.
    """
    rng = np.random.default_rng(seed)
    years = np.arange(2061, 2061 + n_years)
    levels = 1.7 + rng.normal(0, 0.40, size=(n_loc, n_draw))
    phi, sigma = 0.85, 0.06
    tfr = np.empty((n_years, n_loc, n_draw))
    state = levels.copy()
    for t in range(n_years):
        state = levels + phi * (state - levels) + rng.normal(0, sigma, state.shape)
        tfr[t] = state
    gain = 0.11
    e0_female = 80.0 + gain * np.arange(n_years)[:, None, None] + rng.normal(
        0, 0.3, (n_years, n_loc, n_draw)
    )
    e0_male = e0_female - 4.0
    loc_id = np.arange(n_loc)
    return years, tfr, e0_female, e0_male, loc_id


def fitted():
    years, tfr, ef, em, loc_id = synthetic()
    continuation = rates.fit(
        years=years, tfr=tfr, e0_female=ef, e0_male=em, loc_id=loc_id,
        fit_start_year=int(years[0]),
    )
    return years, tfr, ef, em, continuation


def test_fit_recovers_the_within_trajectory_autocorrelation():
    _, _, _, _, continuation = fitted()
    assert np.all(continuation.tfr_phi > 0.7)
    assert np.all(continuation.tfr_phi < 0.95)


def test_fit_recovers_the_longevity_drift():
    _, _, _, _, continuation = fitted()
    assert np.allclose(continuation.e0_drift, 0.11, atol=0.02)


def test_between_draw_spread_survives():
    """The failure this module was written to avoid.

    Pooling trajectories when fitting would centre every path on one country
    level, so the spread across draws would collapse toward the stationary
    within-path spread. It must instead stay close to what it was at the
    boundary.
    """
    years, tfr, ef, em, continuation = fitted()
    _, extended, _, _, _ = rates.extend(
        years=years, tfr=tfr, e0_female=ef, e0_male=em,
        continuation=continuation, end_year=int(years[-1]) + 50, seed=3,
    )
    before = extended[len(years) - 1].std(axis=1)
    after = extended[-1].std(axis=1)
    assert np.all(after > 0.8 * before), "the ensemble spread collapsed"
    assert np.all(after < 1.6 * before), "the paths ran away from their levels"


def test_continuation_starts_from_each_path_own_boundary_value():
    years, tfr, ef, em, continuation = fitted()
    _, extended, _, _, _ = rates.extend(
        years=years, tfr=tfr, e0_female=ef, e0_male=em,
        continuation=continuation, end_year=int(years[-1]) + 30, seed=3,
    )
    # One step past the boundary is the boundary value pulled by phi plus noise,
    # so it must still track each path's own level rather than a common one.
    boundary, first = tfr[-1], extended[len(years)]
    assert np.corrcoef(boundary.ravel(), first.ravel())[0, 1] > 0.9


def test_longevity_keeps_improving_rather_than_freezing():
    years, tfr, ef, em, continuation = fitted()
    _, _, e0, male, _ = rates.extend(
        years=years, tfr=tfr, e0_female=ef, e0_male=em,
        continuation=continuation, end_year=int(years[-1]) + 50, seed=3,
    )
    assert e0[-1].mean() > ef[-1].mean() + 3.0
    assert np.all(e0[-1] > male[-1]), "the sexes crossed"


def test_source_years_are_returned_unchanged():
    years, tfr, ef, em, continuation = fitted()
    out_years, out_tfr, out_ef, out_em, _ = rates.extend(
        years=years, tfr=tfr, e0_female=ef, e0_male=em,
        continuation=continuation, end_year=int(years[-1]) + 10, seed=3,
    )
    n = len(years)
    assert np.array_equal(out_years[:n], years)
    assert np.array_equal(out_tfr[:n], tfr)
    assert np.array_equal(out_ef[:n], ef)
    assert np.array_equal(out_em[:n], em)


def test_extension_is_reproducible_from_its_seed():
    years, tfr, ef, em, continuation = fitted()
    runs = [
        rates.extend(
            years=years, tfr=tfr, e0_female=ef, e0_male=em,
            continuation=continuation, end_year=int(years[-1]) + 20, seed=11,
        )[1]
        for _ in range(2)
    ]
    assert np.array_equal(*runs)


def test_rails_are_taken_from_the_source_not_written_down():
    """A rail that fires on ordinary source behaviour is a silent model."""
    years, tfr, ef, em, continuation = fitted()
    *_, diagnostics = rates.extend(
        years=years, tfr=tfr, e0_female=ef, e0_male=em,
        continuation=continuation, end_year=int(years[-1]) + 50, seed=3,
    )
    low, high = diagnostics["rails"]["sex_gap"]
    assert low <= float((ef - em).min()) and high >= float((ef - em).max())
    assert diagnostics["rails"]["tfr"][0] > 0, "fertility rail allows a negative rate"
    assert diagnostics["clipped_share"] < 1e-3


def test_a_short_fit_window_raises_rather_than_guesses():
    years, tfr, ef, em, loc_id = synthetic(n_years=40)
    with pytest.raises(rates.RateContinuationError):
        rates.fit(
            years=years, tfr=tfr, e0_female=ef, e0_male=em, loc_id=loc_id,
            fit_start_year=int(years[-5]),
        )


def test_extending_backwards_raises():
    years, tfr, ef, em, continuation = fitted()
    with pytest.raises(rates.RateContinuationError):
        rates.extend(
            years=years, tfr=tfr, e0_female=ef, e0_male=em,
            continuation=continuation, end_year=int(years[-1]), seed=3,
        )

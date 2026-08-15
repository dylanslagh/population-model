"""Transparent post-WPP migration continuation.

The UN's published projection ends at 2100.  UW's public ``bayesMig`` archive
contains 1,000 country-level net-migration-rate trajectories through that date,
but not the fitted MCMC state that generated them.  This module therefore does
not claim to continue an official UN projection.  It emulates the published
late-horizon generating process with the same AR(1) form, begins every path at
its own published 2100 value, and labels the result a project extension.

Two accounting constraints are imposed during projection:

* annual world net migration is exactly zero for every trajectory; and
* net emigration cannot remove more people from an age/sex cell than exist.

The first is required because the public UW trajectories are not globally
balanced draw by draw.  The UN applies a more detailed three-stage balancing
procedure; the population-weighted balancing here is a documented
approximation, not a reproduction of that unpublished trajectory state.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from popmodel.engine import cohort
from popmodel.ingest.uw_mig import MigrationIngestError, MigrationRateDraws, RATE_LIMIT

DEFAULT_FIT_START_YEAR = 2070
DEFAULT_SEED = 20260814


@dataclass(frozen=True)
class Ar1Continuation:
    """Country-level late-horizon AR(1) approximation to published paths."""

    loc_id: np.ndarray
    mu: np.ndarray
    phi: np.ndarray
    sigma: np.ndarray
    fit_start_year: int
    fit_end_year: int
    phi_clipped: int
    source: str

    def __post_init__(self) -> None:
        arrays = tuple(np.asarray(v, dtype=np.float64) for v in (self.mu, self.phi, self.sigma))
        n = len(np.asarray(self.loc_id))
        if any(v.shape != (n,) for v in arrays):
            raise ValueError("AR(1) parameter arrays must match loc_id")
        if not all(np.all(np.isfinite(v)) for v in arrays):
            raise ValueError("AR(1) parameters contain non-finite values")
        if np.any((arrays[1] < 0) | (arrays[1] >= 1)):
            raise ValueError("AR(1) phi must be in [0, 1)")
        if np.any(arrays[2] <= 0):
            raise ValueError("AR(1) sigma must be positive")
        object.__setattr__(self, "loc_id", np.asarray(self.loc_id, dtype=np.int64))
        object.__setattr__(self, "mu", arrays[0])
        object.__setattr__(self, "phi", arrays[1])
        object.__setattr__(self, "sigma", arrays[2])


@dataclass(frozen=True)
class SimulatedMigrationRates:
    """Post-2100 migration rates in source location order."""

    years: np.ndarray  # rate years, inclusive
    loc_id: np.ndarray
    trajectory_ids: np.ndarray
    rates: np.ndarray  # (D, T, L)
    seed: int
    clipped_values: int
    generated_values: int


@dataclass(frozen=True)
class RawMigrationPath:
    """One UW trajectory, observed through 2100 and emulated afterwards.

    These are deliberately *raw* rates.  They are shared by the reference and
    selection runs.  Each run balances them against its own evolving
    population, because applying a count balanced for one population to the
    other would quietly create or remove people.
    """

    years: np.ndarray  # rate years, inclusive
    loc_id: np.ndarray
    trajectory_id: int
    rates: np.ndarray  # (T, L), in source-location order
    continuation_seed: int


def trajectory_path(
    draws: MigrationRateDraws,
    continuation: SimulatedMigrationRates,
    *,
    trajectory_id: int,
    start_rate_year: int,
    end_rate_year: int,
) -> RawMigrationPath:
    """Join one source path to its matching post-2100 continuation.

    The trajectory identity is shared across countries because it is the only
    cross-country dependence exposed by the UW archive.  The continuation was
    simulated for every source trajectory with one pinned seed, so selecting
    this row also selects its exact future innovations.
    """
    if not np.array_equal(draws.loc_id, continuation.loc_id):
        raise ValueError("source and continuation locations do not match")
    if not np.array_equal(draws.trajectory_ids, continuation.trajectory_ids):
        raise ValueError("source and continuation trajectory IDs do not match")
    if start_rate_year < int(draws.years[0]) or end_rate_year < start_rate_year:
        raise ValueError("requested migration years are outside the source range")
    source_row = np.flatnonzero(draws.trajectory_ids == int(trajectory_id))
    if len(source_row) != 1:
        raise ValueError(f"unknown migration trajectory ID {trajectory_id}")
    row = int(source_row[0])
    years = np.arange(start_rate_year, end_rate_year + 1, dtype=np.int64)
    rates = np.empty((len(years), len(draws.loc_id)), dtype=np.float64)
    observed = years <= int(draws.years[-1])
    if np.any(observed):
        indices = years[observed] - int(draws.years[0])
        rates[observed] = draws.rates[row, indices, :]
    if np.any(~observed):
        indices = years[~observed] - int(continuation.years[0])
        if np.any(indices < 0) or np.any(indices >= len(continuation.years)):
            raise ValueError("continuation does not cover every requested migration year")
        rates[~observed] = continuation.rates[row, indices, :]
    return RawMigrationPath(
        years=years,
        loc_id=np.asarray(draws.loc_id, dtype=np.int64),
        trajectory_id=int(trajectory_id),
        rates=rates,
        continuation_seed=int(continuation.seed),
    )


@dataclass
class BalancedMigrationPath:
    """Apply one raw path without letting balancing depend on hidden counts.

    ``movement`` is called once per rate year by the cohort engine.  It records
    the adjustment imposed by world balancing, which makes the necessary
    population-dependence of a paired comparison inspectable rather than an
    unreported source of differences.
    """

    raw: RawMigrationPath
    rates: np.ndarray  # (T, L), aligned to the engine locations
    composition: np.ndarray  # (L, 2, 101)
    active_locations: np.ndarray
    locations: tuple[str, ...]
    _step: int = 0
    _maximum_world_imbalance_people: float = 0.0
    _maximum_rate_adjustment: float = 0.0
    _total_absolute_adjustment_people: float = 0.0
    _redistributed_outflow_cells: int = 0

    def __post_init__(self) -> None:
        self.rates = np.asarray(self.rates, dtype=np.float64)
        self.composition = np.asarray(self.composition, dtype=np.float64)
        self.active_locations = np.asarray(self.active_locations, dtype=bool)
        n_locations = len(self.locations)
        if self.rates.shape != (len(self.raw.years), n_locations):
            raise ValueError("aligned migration rates do not match years or locations")
        if self.composition.shape != (n_locations, cohort.N_SEXES, cohort.N_AGES):
            raise ValueError("migration composition does not match locations")
        if self.active_locations.shape != (n_locations,):
            raise ValueError("active migration locations do not match locations")
        if np.any(self.composition < 0) or not np.allclose(
            self.composition.sum(axis=(1, 2)), 1.0, atol=1e-10
        ):
            raise ValueError("migration composition must be non-negative and sum to one")

    def movement(
        self,
        start_population: np.ndarray,
        available_population: np.ndarray,
    ) -> np.ndarray:
        """Return this year's feasible age/sex migration, recording its receipt."""
        if self._step >= len(self.raw.years):
            raise ValueError("migration path was asked for more years than it contains")
        start = np.asarray(start_population, dtype=np.float64)
        available = np.asarray(available_population, dtype=np.float64)
        if start.shape != (len(self.locations),):
            raise ValueError("start population does not match migration locations")
        if available.shape != (len(self.locations), cohort.N_SEXES, cohort.N_AGES):
            raise ValueError("available population does not match migration locations")
        requested = self.rates[self._step]
        requested_counts = requested * start
        adjusted, net_counts = balance_rates(
            requested, start, active=self.active_locations,
            lower=-RATE_LIMIT, upper=RATE_LIMIT,
        )
        self._maximum_world_imbalance_people = max(
            self._maximum_world_imbalance_people,
            float(abs(net_counts.sum())),
        )
        self._maximum_rate_adjustment = max(
            self._maximum_rate_adjustment,
            float(np.max(np.abs(adjusted - requested))),
        )
        self._total_absolute_adjustment_people += float(
            np.abs(net_counts - requested_counts).sum()
        )
        movement, redistributed = allocate_age_sex_migration(
            net_counts[None, :], available[None, :, :, :], self.composition
        )
        self._redistributed_outflow_cells += int(redistributed)
        self._step += 1
        return movement[0]

    def receipt(self) -> dict:
        """The run-specific accounting record for a shared raw path."""
        if self._step != len(self.raw.years):
            raise ValueError("cannot receipt a migration path before every year is used")
        return {
            "source_trajectory_id": self.raw.trajectory_id,
            "continuation_seed": self.raw.continuation_seed,
            "rate_years": [int(self.raw.years[0]), int(self.raw.years[-1])],
            "maximum_world_imbalance_people": self._maximum_world_imbalance_people,
            "maximum_rate_adjustment": self._maximum_rate_adjustment,
            "total_absolute_adjustment_people": self._total_absolute_adjustment_people,
            "redistributed_outflow_cells": self._redistributed_outflow_cells,
            "world_balance": "zero net migrants every year after population-weighted adjustment",
        }


@dataclass(frozen=True)
class MigrationExtensionResult:
    """Country totals from migration-only uncertainty after the UN boundary."""

    years: np.ndarray  # population dates, start through end inclusive
    locations: tuple[str, ...]
    trajectory_ids: np.ndarray
    location_totals: np.ndarray  # (D, Y, L)
    maximum_world_imbalance_people: float
    redistributed_outflow_cells: int

    @property
    def world(self) -> np.ndarray:
        return self.location_totals.sum(axis=2)


def fit_late_ar1(
    draws: MigrationRateDraws,
    *,
    fit_start_year: int = DEFAULT_FIT_START_YEAR,
    phi_max: float = 0.995,
) -> Ar1Continuation:
    """Estimate the late-horizon AR(1) transition represented by UW's paths.

    This is an emulator fit to model output, not an independently estimated
    demographic mechanism.  Pooling all 1,000 paths for each country makes the
    transition estimate stable while preserving uncertainty in every path's
    2100 starting value and in its future innovations.
    """
    years = np.asarray(draws.years, dtype=np.int64)
    matches = np.flatnonzero(years == int(fit_start_year))
    if len(matches) != 1 or fit_start_year >= int(years[-1]):
        raise MigrationIngestError(
            f"AR(1) fit start {fit_start_year} must occur before {int(years[-1])}"
        )
    if not 0 < phi_max < 1:
        raise ValueError("phi_max must be strictly between zero and one")

    start = int(matches[0])
    x = draws.rates[:, start:-1, :].reshape(-1, len(draws.loc_id)).astype(np.float64)
    y = draws.rates[:, start + 1 :, :].reshape(-1, len(draws.loc_id)).astype(np.float64)
    mean_x = x.mean(axis=0)
    mean_y = y.mean(axis=0)
    variance = ((x - mean_x) ** 2).mean(axis=0)
    if np.any(variance <= 0):
        codes = np.asarray(draws.loc_id)[variance <= 0]
        raise MigrationIngestError(f"no late-horizon migration variation for {codes[:5]}")

    raw_phi = (((x - mean_x) * (y - mean_y)).mean(axis=0) / variance)
    phi = np.clip(raw_phi, 0.0, phi_max)
    intercept = mean_y - phi * mean_x
    mu = intercept / (1.0 - phi)
    residual = y - (intercept + phi * x)
    sigma = residual.std(axis=0)

    if np.any(np.abs(mu) > RATE_LIMIT):
        code = int(np.asarray(draws.loc_id)[np.argmax(np.abs(mu))])
        raise MigrationIngestError(
            f"AR(1) long-run mean for LocID {code} is outside +/-{RATE_LIMIT}"
        )
    if np.any(sigma <= 0) or np.any(sigma > RATE_LIMIT):
        raise MigrationIngestError("AR(1) innovation scale is outside the allowed range")

    return Ar1Continuation(
        loc_id=np.asarray(draws.loc_id),
        mu=mu,
        phi=phi,
        sigma=sigma,
        fit_start_year=int(fit_start_year),
        fit_end_year=int(years[-1]),
        phi_clipped=int(np.count_nonzero(phi != raw_phi)),
        source=(
            "pooled country-level AR(1) fitted to UW bayesMig trajectories from "
            f"{fit_start_year} through {int(years[-1])}; model-output emulator"
        ),
    )


def simulate_ar1_continuation(
    draws: MigrationRateDraws,
    model: Ar1Continuation,
    *,
    end_rate_year: int,
    seed: int = DEFAULT_SEED,
    rate_limit: float = RATE_LIMIT,
) -> SimulatedMigrationRates:
    """Continue each source path from its own final value through ``end_rate_year``."""
    if not np.array_equal(draws.loc_id, model.loc_id):
        raise ValueError("migration draws and AR(1) model use different locations")
    start_year = int(draws.years[-1])
    if int(end_rate_year) < start_year:
        raise ValueError(f"end_rate_year must be at least {start_year}")
    years = np.arange(start_year, int(end_rate_year) + 1, dtype=np.int64)
    rates = np.empty(
        (len(draws.trajectory_ids), len(years), len(draws.loc_id)), dtype=np.float32
    )
    rates[:, 0, :] = draws.rates[:, -1, :]
    rng = np.random.default_rng(int(seed))
    clipped = 0
    generated = max(0, rates[:, 1:, :].size)
    for t in range(1, len(years)):
        innovation = rng.normal(0.0, model.sigma, size=(len(draws.trajectory_ids), len(draws.loc_id)))
        value = model.mu + model.phi * (rates[:, t - 1, :] - model.mu) + innovation
        clipped += int(np.count_nonzero((value < -rate_limit) | (value > rate_limit)))
        rates[:, t, :] = np.clip(value, -rate_limit, rate_limit)
    return SimulatedMigrationRates(
        years=years,
        loc_id=np.asarray(draws.loc_id, dtype=np.int64),
        trajectory_ids=np.asarray(draws.trajectory_ids, dtype=np.int64),
        rates=rates,
        seed=int(seed),
        clipped_values=clipped,
        generated_values=generated,
    )


def balance_rates(
    rates: np.ndarray,
    population: np.ndarray,
    *,
    active: np.ndarray | None = None,
    lower: np.ndarray | float = -RATE_LIMIT,
    upper: np.ndarray | float = RATE_LIMIT,
) -> tuple[np.ndarray, np.ndarray]:
    """Make annual net migration counts sum to zero for every draw.

    The correction is a common rate shift across locations that are not at a
    supplied bound.  This is equivalent to redistributing the global count
    discrepancy in proportion to current population.
    """
    original = np.asarray(rates, dtype=np.float64)
    pop = np.asarray(population, dtype=np.float64)
    squeeze = original.ndim == 1
    if squeeze:
        original, pop = original[None, :], pop[None, :]
    if original.ndim != 2 or pop.shape != original.shape:
        raise ValueError("rates and population must have matching (draw, location) shapes")
    if np.any(pop < 0) or not np.all(np.isfinite(pop)):
        raise ValueError("population must be finite and non-negative")

    n_draws, n_locations = original.shape
    active_mask = np.ones(n_locations, dtype=bool) if active is None else np.asarray(active, dtype=bool)
    if active_mask.shape != (n_locations,):
        raise ValueError("active mask must have one entry per location")
    lo = np.broadcast_to(np.asarray(lower, dtype=np.float64), original.shape)
    hi = np.broadcast_to(np.asarray(upper, dtype=np.float64), original.shape)
    if np.any(lo > hi):
        raise ValueError("lower migration-rate bounds exceed upper bounds")

    adjusted = np.where(active_mask[None, :], np.clip(original, lo, hi), 0.0)
    free = np.broadcast_to(active_mask, adjusted.shape).copy()
    for _ in range(n_locations + 1):
        residual = (adjusted * pop).sum(axis=1)
        tolerance = np.maximum(1e-6, pop.sum(axis=1) * 1e-13)
        unfinished = np.abs(residual) > tolerance
        if not np.any(unfinished):
            break
        denominator = (pop * free).sum(axis=1)
        if np.any(unfinished & (denominator <= 0)):
            raise ValueError("global migration cannot be balanced within the supplied bounds")
        shift = np.divide(residual, denominator, out=np.zeros_like(residual), where=denominator > 0)
        candidate = adjusted - shift[:, None] * free
        hit_low = free & (candidate < lo)
        hit_high = free & (candidate > hi)
        adjusted = np.where(hit_low, lo, np.where(hit_high, hi, candidate))
        free &= ~(hit_low | hit_high)
    else:
        raise ValueError("global migration balancing did not converge")

    counts = adjusted * pop
    tolerance = np.maximum(1e-5, pop.sum(axis=1) * 2e-13)
    if np.any(np.abs(counts.sum(axis=1)) > tolerance):
        worst = float(np.abs(counts.sum(axis=1)).max())
        raise ValueError(f"global migration remains unbalanced by {worst:.3f} people")
    if squeeze:
        return adjusted[0], counts[0]
    return adjusted, counts


def allocate_age_sex_migration(
    net_counts: np.ndarray,
    available_population: np.ndarray,
    composition: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Allocate country totals without letting emigration create negative cells.

    Immigration follows the borrowed age/sex schedule directly.  Emigration
    starts from that schedule, but when it asks to remove more people from a
    cell than exist, the unmet amount is redistributed across the remaining
    populated cells.  This preserves the country total instead of relying on
    the cohort engine's final zero clip, which would silently create people.
    """
    counts = np.asarray(net_counts, dtype=np.float64)
    available = np.asarray(available_population, dtype=np.float64)
    shares = np.asarray(composition, dtype=np.float64)
    if counts.ndim != 2 or available.shape[:2] != counts.shape:
        raise ValueError("net counts and available population use different draws or locations")
    if available.shape[2:] != (cohort.N_SEXES, cohort.N_AGES):
        raise ValueError("available population must have age and sex axes")
    if shares.shape != available.shape[1:]:
        raise ValueError("migration composition does not match available population")

    movement = np.maximum(counts, 0.0)[:, :, None, None] * shares[None, :, :, :]
    negative = counts < 0
    if not np.any(negative):
        return movement, 0

    target = (-counts[negative]).astype(np.float64)
    cells = cohort.N_SEXES * cohort.N_AGES
    capacity = available[negative].reshape(-1, cells).copy()
    base_weight = np.broadcast_to(shares, available.shape[1:])[None, ...]
    base_weight = np.broadcast_to(base_weight, available.shape)[negative].reshape(-1, cells)
    allocated = np.zeros_like(capacity)
    remaining = target.copy()
    redistributed = 0

    for _ in range(cells + 1):
        unfinished = remaining > np.maximum(1e-8, target * 1e-12)
        if not np.any(unfinished):
            break
        free = capacity > 1e-10
        weight = np.where(free, base_weight, 0.0)
        weight_sum = weight.sum(axis=1)
        fallback = unfinished & (weight_sum <= 0)
        if np.any(fallback):
            weight[fallback] = capacity[fallback]
            weight_sum = weight.sum(axis=1)
        if np.any(unfinished & (weight_sum <= 0)):
            raise ValueError("net emigration exceeds the population available to remove")
        proposed = np.divide(
            remaining[:, None] * weight,
            weight_sum[:, None],
            out=np.zeros_like(weight),
            where=weight_sum[:, None] > 0,
        )
        hit = proposed > capacity
        redistributed += int(np.count_nonzero(hit))
        taken = np.minimum(proposed, capacity)
        allocated += taken
        capacity -= taken
        remaining -= taken.sum(axis=1)
    else:
        raise ValueError("age/sex emigration allocation did not converge")

    if np.any(remaining > np.maximum(1e-6, target * 1e-10)):
        raise ValueError("age/sex emigration allocation left an unallocated remainder")
    movement[negative] = -allocated.reshape(-1, cohort.N_SEXES, cohort.N_AGES)
    produced = movement.sum(axis=(2, 3))
    if not np.allclose(produced, counts, rtol=0, atol=1e-5):
        raise ValueError("age/sex migration does not reproduce country net counts")
    return movement, redistributed


def project_extension(
    pop_start: np.ndarray,
    *,
    start_year: int,
    end_year: int,
    sx: np.ndarray,
    asfr: np.ndarray,
    srb: np.ndarray,
    rate_years: np.ndarray,
    rate_paths: np.ndarray,
    composition: np.ndarray,
    locations: tuple[str, ...],
    trajectory_ids: np.ndarray,
    active_locations: np.ndarray | None = None,
    batch_size: int = 25,
) -> MigrationExtensionResult:
    """Project one common boundary population under stochastic migration rates.

    Fertility, mortality and the sex ratio are common to all migration draws.
    Each can be either one fixed schedule or a time series; a shorter time
    series holds its last supplied schedule.  Only migration varies.  Batching
    keeps 1,000 paths from requiring several gigabytes of simultaneous
    age-by-sex population state.
    """
    pop0 = np.asarray(pop_start, dtype=np.float64)
    rates = np.asarray(rate_paths, dtype=np.float64)
    rate_years = np.asarray(rate_years, dtype=np.int64)
    sx = np.asarray(sx, dtype=np.float64)
    asfr = np.asarray(asfr, dtype=np.float64)
    srb = np.asarray(srb, dtype=np.float64)
    composition = np.asarray(composition, dtype=np.float64)
    active = (
        np.ones(pop0.shape[0], dtype=bool)
        if active_locations is None
        else np.asarray(active_locations, dtype=bool)
    )
    n_locations = pop0.shape[0]
    n_draws = rates.shape[0]
    n_steps = int(end_year) - int(start_year)
    expected_pop = (n_locations, cohort.N_SEXES, cohort.N_AGES)
    if pop0.shape != expected_pop:
        raise ValueError(f"pop_start must be {expected_pop}; got {pop0.shape}")
    if rates.shape != (n_draws, n_steps, n_locations):
        raise ValueError(
            f"rate_paths must be ({n_draws}, {n_steps}, {n_locations}); got {rates.shape}"
        )
    if not np.array_equal(rate_years, np.arange(start_year, end_year)):
        raise ValueError("rate years must cover every projection year exactly")
    sx_shapes = ((n_locations, cohort.N_SEXES, cohort.N_AGES), (None, n_locations, cohort.N_SEXES, cohort.N_AGES))
    asfr_shapes = ((n_locations, cohort.N_AGES), (None, n_locations, cohort.N_AGES))
    srb_shapes = ((n_locations,), (None, n_locations))
    if sx.shape != sx_shapes[0] and not (sx.ndim == 4 and sx.shape[1:] == sx_shapes[1][1:]):
        raise ValueError("sx has the wrong shape")
    if asfr.shape != asfr_shapes[0] and not (
        asfr.ndim == 3 and asfr.shape[1:] == asfr_shapes[1][1:]
    ):
        raise ValueError("asfr has the wrong shape")
    if srb.shape != srb_shapes[0] and not (srb.ndim == 2 and srb.shape[1:] == srb_shapes[1][1:]):
        raise ValueError("srb has the wrong shape")
    if composition.shape != expected_pop:
        raise ValueError("migration composition has the wrong shape")
    if len(locations) != n_locations or active.shape != (n_locations,):
        raise ValueError("location labels or active mask do not match the population")
    if len(trajectory_ids) != n_draws:
        raise ValueError("trajectory IDs do not match migration paths")
    if np.any(pop0 < 0) or not np.all(np.isfinite(pop0)):
        raise ValueError("boundary population must be finite and non-negative")
    if np.any(composition < 0) or not np.allclose(
        composition.sum(axis=(1, 2)), 1.0, atol=1e-10
    ):
        raise ValueError("each location's migration composition must be non-negative and sum to one")

    totals = np.empty((n_draws, n_steps + 1, n_locations), dtype=np.float64)
    max_imbalance = 0.0
    redistributed = 0
    for first in range(0, n_draws, int(batch_size)):
        last = min(first + int(batch_size), n_draws)
        pop = np.broadcast_to(pop0, (last - first,) + pop0.shape).copy()
        totals[first:last, 0, :] = pop.sum(axis=(2, 3))
        for t in range(n_steps):
            sx_t = sx if sx.ndim == 3 else sx[min(t, len(sx) - 1)]
            asfr_t = asfr if asfr.ndim == 2 else asfr[min(t, len(asfr) - 1)]
            srb_t = srb if srb.ndim == 1 else srb[min(t, len(srb) - 1)]
            aged = np.zeros_like(pop)
            aged[:, :, :, 1 : cohort.MAX_AGE] = (
                pop[:, :, :, 0 : cohort.MAX_AGE - 1] * sx_t[None, :, :, 1 : cohort.MAX_AGE]
            )
            aged[:, :, :, cohort.MAX_AGE] = (
                pop[:, :, :, cohort.MAX_AGE - 1] + pop[:, :, :, cohort.MAX_AGE]
            ) * sx_t[None, :, :, cohort.MAX_AGE]

            start_totals = pop.sum(axis=(2, 3))
            requested = rates[first:last, t, :]
            _, net_counts = balance_rates(
                requested,
                start_totals,
                active=active,
                lower=-RATE_LIMIT,
                upper=RATE_LIMIT,
            )
            imbalance = np.abs(net_counts.sum(axis=1))
            max_imbalance = max(max_imbalance, float(imbalance.max(initial=0.0)))
            movement, n_redistributed = allocate_age_sex_migration(
                net_counts, aged, composition
            )
            redistributed += n_redistributed
            aged += movement

            exposure = 0.5 * (pop[:, :, cohort.FEMALE, :] + aged[:, :, cohort.FEMALE, :])
            births = np.einsum("bla,la->bl", exposure, asfr_t)
            female_share = 1.0 / (1.0 + srb_t)
            aged[:, :, cohort.FEMALE, 0] += births * female_share * sx_t[:, cohort.FEMALE, 0]
            aged[:, :, cohort.MALE, 0] += births * (1.0 - female_share) * sx_t[:, cohort.MALE, 0]
            if np.any(aged < -1e-7):
                raise ValueError("migration removed more people than an age/sex cell contained")
            np.maximum(aged, 0.0, out=aged)
            pop = aged
            totals[first:last, t + 1, :] = pop.sum(axis=(2, 3))

    return MigrationExtensionResult(
        years=np.arange(start_year, end_year + 1, dtype=np.int64),
        locations=tuple(locations),
        trajectory_ids=np.asarray(trajectory_ids, dtype=np.int64),
        location_totals=totals,
        maximum_world_imbalance_people=max_imbalance,
        redistributed_outflow_cells=redistributed,
    )

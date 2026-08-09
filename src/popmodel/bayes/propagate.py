"""Stage 2 of the Bayesian workflow: propagate already-fitted rate draws.

Nothing in this module fits a model. A fitting or source-adapter step upstream
must produce one :class:`ProjectionDraw` for each prior or posterior sample. Fertility
and mortality live in the same object, with their original component IDs and a
statement of how separately fitted chains were coupled. Merely putting two
arrays beside each other does not turn independent fits into a joint posterior.

Each draw advances through the cohort engine one year at a time. Only country
totals are retained, so memory is bounded by one population state rather than a
full country-by-age history for every year and draw.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Protocol

import numpy as np

from popmodel.engine import cohort


def _readonly_array(value) -> np.ndarray:
    """Own a validated buffer so callers cannot mutate it behind provenance."""
    out = np.array(value, copy=True)
    out.setflags(write=False)
    return out


def _years(value, name: str) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1 or len(raw) == 0:
        raise ValueError(f"{name} must be a non-empty one-dimensional array")
    if not np.issubdtype(raw.dtype, np.integer):
        if not np.all(np.isfinite(raw)) or not np.all(raw == np.floor(raw)):
            raise ValueError(f"{name} must contain whole calendar years")
    years = raw.astype(np.int64, copy=True)
    if len(years) > 1 and not np.all(np.diff(years) == 1):
        raise ValueError(f"{name} must be consecutive calendar years")
    years.setflags(write=False)
    return years


def _locations(value, name: str) -> tuple[str, ...]:
    locations = tuple(str(code).strip() for code in value)
    if not locations or any(not code for code in locations):
        raise ValueError(f"{name} must contain non-empty location codes")
    if len(set(locations)) != len(locations):
        raise ValueError(f"{name} contains duplicate location codes")
    return locations


def _text(value: str, name: str) -> str:
    out = str(value).strip()
    if not out:
        raise ValueError(f"{name} must be stated")
    return out


@dataclass(frozen=True)
class SeriesExtension:
    """What to do when a projected year lies beyond a supplied series."""

    mode: str
    rationale: str

    def __post_init__(self) -> None:
        if self.mode not in {"error", "hold-last"}:
            raise ValueError("extension mode must be 'error' or 'hold-last'")
        object.__setattr__(self, "rationale", _text(
            self.rationale, "extension rationale"
        ))

    @classmethod
    def require_source(cls) -> "SeriesExtension":
        return cls("error", "the source must cover every projected rate year")

    @classmethod
    def hold_last(cls, rationale: str) -> "SeriesExtension":
        return cls("hold-last", rationale)


@dataclass(frozen=True)
class RateExtensionPolicy:
    """Separate extension rules for the three demographic rate components."""

    fertility: SeriesExtension
    mortality: SeriesExtension
    sex_ratio: SeriesExtension

    @classmethod
    def strict(cls) -> "RateExtensionPolicy":
        required = SeriesExtension.require_source()
        return cls(fertility=required, mortality=required, sex_ratio=required)

    @classmethod
    def hold_all(cls, rationale: str) -> "RateExtensionPolicy":
        held = SeriesExtension.hold_last(rationale)
        return cls(fertility=held, mortality=held, sex_ratio=held)


@dataclass(frozen=True)
class BasePopulation:
    """The shared starting state, including the evidence it came from."""

    year: int
    locations: tuple[str, ...]
    values: np.ndarray  # (L, 2, 101), people on 1 January
    source_revision: str
    source: str

    def __post_init__(self) -> None:
        if int(self.year) != self.year:
            raise ValueError("base population year must be a whole calendar year")
        object.__setattr__(self, "year", int(self.year))
        locations = _locations(self.locations, "base population locations")
        values = _readonly_array(self.values)
        object.__setattr__(self, "locations", locations)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "source_revision", _text(
            self.source_revision, "base population source revision"
        ))
        object.__setattr__(self, "source", _text(
            self.source, "base population source"
        ))
        expected = (len(locations), cohort.N_SEXES, cohort.N_AGES)
        if values.shape != expected:
            raise ValueError(f"base population must be {expected}; got {values.shape}")
        if not np.all(np.isfinite(values)):
            raise ValueError("base population contains non-finite values")
        if np.any(values < 0):
            raise ValueError("base population contains negative people")


@dataclass(frozen=True)
class DrawProvenance:
    """Where one paired rate draw came from and how it was assembled."""

    source_revision: str
    fertility_source: str
    mortality_source: str
    fertility_draw_id: str
    mortality_draw_id: str
    coupling_method: str
    rate_conversion: str

    def __post_init__(self) -> None:
        for name in (
            "source_revision", "fertility_source", "mortality_source",
            "fertility_draw_id", "mortality_draw_id", "coupling_method",
            "rate_conversion",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def model_identity(self) -> tuple[str, ...]:
        """Provenance that should be common across draws, excluding sample IDs."""
        return (
            self.source_revision,
            self.fertility_source,
            self.mortality_source,
            self.coupling_method,
            self.rate_conversion,
        )


@dataclass(frozen=True)
class TrajectoryProvenance:
    """Identity of compact TFR/e0 components before schedule conversion."""

    source_revision: str
    fertility_source: str
    mortality_source: str
    fertility_draw_id: str
    mortality_draw_id: str
    coupling_method: str

    def __post_init__(self) -> None:
        for name in (
            "source_revision", "fertility_source", "mortality_source",
            "fertility_draw_id", "mortality_draw_id", "coupling_method",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def model_identity(self) -> tuple[str, ...]:
        return (
            self.source_revision,
            self.fertility_source,
            self.mortality_source,
            self.coupling_method,
        )


@dataclass(frozen=True)
class TrajectoryDraw:
    """Compact demographic trajectories, explicitly not engine-ready rates.

    UW supplies total fertility and female/male life expectancy. It does not
    supply the age-specific fertility and survival schedules required by the
    cohort engine in these archives. A :class:`ScheduleConverter` must perform
    that separate, versioned expansion.
    """

    draw_id: str
    years: np.ndarray  # (T,)
    locations: tuple[str, ...]
    tfr: np.ndarray  # (T, L), births per woman
    e0_female: np.ndarray  # (T, L), years
    e0_male: np.ndarray  # (T, L), years
    draw_kind: str  # "prior" or "posterior"
    weight: float
    provenance: TrajectoryProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "draw_id", _text(self.draw_id, "draw_id"))
        if self.draw_kind not in {"prior", "posterior"}:
            raise ValueError("draw_kind must be 'prior' or 'posterior'")
        if not np.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("draw weight must be finite and positive")
        object.__setattr__(self, "weight", float(self.weight))
        if not isinstance(self.provenance, TrajectoryProvenance):
            raise TypeError("trajectory provenance must be TrajectoryProvenance")

        years = _years(self.years, "trajectory years")
        locations = _locations(self.locations, "trajectory locations")
        object.__setattr__(self, "years", years)
        object.__setattr__(self, "locations", locations)
        expected = (len(years), len(locations))
        for name in ("tfr", "e0_female", "e0_male"):
            arr = _readonly_array(getattr(self, name))
            object.__setattr__(self, name, arr)
            if arr.shape != expected:
                raise ValueError(f"{name} must be {expected}; got {arr.shape}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{name} contains non-finite values")
            if np.any(arr < 0 if name == "tfr" else arr <= 0):
                qualifier = "non-negative" if name == "tfr" else "positive"
                raise ValueError(f"{name} must be {qualifier}")


class TrajectoryDrawSource(Protocol):
    """An adapter over native source objects, yielding compact trajectories."""

    def __iter__(self) -> Iterator[TrajectoryDraw]: ...


class ScheduleConverter(Protocol):
    """A versioned TFR/e0-to-age-schedule implementation."""

    name: str
    version: str

    def convert(self, draw: TrajectoryDraw) -> "ProjectionDraw": ...


@dataclass(frozen=True)
class ProjectionDraw:
    """One paired sample, converted to inputs the cohort engine understands."""

    draw_id: str
    years: np.ndarray  # (T,) rate years
    locations: tuple[str, ...]
    sx: np.ndarray  # (T, L, 2, 101), survival into age a
    asfr: np.ndarray  # (T, L, 101), births per woman per year
    srb: np.ndarray  # (T, L), male births per female birth
    draw_kind: str  # "prior" or "posterior"
    weight: float  # only equal-weight ensembles are supported initially
    provenance: DrawProvenance
    extension: RateExtensionPolicy

    def __post_init__(self) -> None:
        object.__setattr__(self, "draw_id", _text(self.draw_id, "draw_id"))
        if self.draw_kind not in {"prior", "posterior"}:
            raise ValueError("draw_kind must be 'prior' or 'posterior'")
        if not np.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("draw weight must be finite and positive")
        object.__setattr__(self, "weight", float(self.weight))
        if not isinstance(self.provenance, DrawProvenance):
            raise TypeError("provenance must be DrawProvenance")
        if not isinstance(self.extension, RateExtensionPolicy):
            raise TypeError("extension must be RateExtensionPolicy")

        years = _years(self.years, "years")
        locations = _locations(self.locations, "locations")
        object.__setattr__(self, "years", years)
        object.__setattr__(self, "locations", locations)

        sx = _readonly_array(self.sx)
        asfr = _readonly_array(self.asfr)
        srb = _readonly_array(self.srb)
        object.__setattr__(self, "sx", sx)
        object.__setattr__(self, "asfr", asfr)
        object.__setattr__(self, "srb", srb)

        t, loc = len(years), len(locations)
        expected = {
            "sx": (t, loc, cohort.N_SEXES, cohort.N_AGES),
            "asfr": (t, loc, cohort.N_AGES),
            "srb": (t, loc),
        }
        for name, arr in (("sx", sx), ("asfr", asfr), ("srb", srb)):
            if arr.shape != expected[name]:
                raise ValueError(f"{name} must be {expected[name]}; got {arr.shape}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{name} contains non-finite values")

        if np.any((sx < 0) | (sx > 1)):
            raise ValueError("sx must stay between zero and one")
        if np.any(asfr < 0):
            raise ValueError("asfr contains negative rates")
        outside = (
            np.count_nonzero(asfr[..., :cohort.FERT_AGE_MIN])
            + np.count_nonzero(asfr[..., cohort.FERT_AGE_MAX + 1:])
        )
        if outside:
            raise ValueError(
                f"asfr is non-zero outside ages {cohort.FERT_AGE_MIN}-"
                f"{cohort.FERT_AGE_MAX}"
            )
        if np.any(srb <= 0):
            raise ValueError("srb must be positive")


class ProjectionDrawSource(Protocol):
    """A source adapter that yields engine-ready samples without stacking them."""

    def __iter__(self) -> Iterator[ProjectionDraw]: ...


@dataclass(frozen=True)
class MigrationAssumption:
    """A shared migration path with enough paperwork to judge what it means."""

    years: np.ndarray  # (T,)
    locations: tuple[str, ...]
    values: np.ndarray  # (T, L, 2, 101)
    source: str
    independently_sourced: bool
    extension: SeriesExtension
    scenario_knob: str | None = None

    def __post_init__(self) -> None:
        if type(self.independently_sourced) is not bool:
            raise TypeError("independently_sourced must be true or false")
        if not isinstance(self.extension, SeriesExtension):
            raise TypeError("migration extension must be SeriesExtension")
        years = _years(self.years, "migration years")
        locations = _locations(self.locations, "migration locations")
        values = _readonly_array(self.values)
        source = _text(self.source, "migration source")
        object.__setattr__(self, "years", years)
        object.__setattr__(self, "locations", locations)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "source", source)

        expected = (len(years), len(locations), cohort.N_SEXES, cohort.N_AGES)
        if values.shape != expected:
            raise ValueError(f"migration values must be {expected}; got {values.shape}")
        if not np.all(np.isfinite(values)):
            raise ValueError("migration values contain non-finite values")
        if not self.independently_sourced:
            knob = str(self.scenario_knob or "").strip()
            if not knob:
                raise ValueError(
                    "non-independent migration must be labelled as a scenario knob"
                )
            object.__setattr__(self, "scenario_knob", knob)

    @classmethod
    def zero(cls, years, locations) -> "MigrationAssumption":
        """Construct an explicit zero-migration assumption for supplied years."""
        clean_years = _years(years, "zero-migration years")
        clean_locations = _locations(locations, "zero-migration locations")
        values = np.zeros((
            len(clean_years), len(clean_locations), cohort.N_SEXES, cohort.N_AGES
        ))
        return cls(
            years=clean_years,
            locations=clean_locations,
            values=values,
            source="explicit zero-migration assumption",
            independently_sourced=False,
            extension=SeriesExtension.require_source(),
            scenario_knob="net migration fixed at zero",
        )


@dataclass(frozen=True)
class ProjectionQuantiles:
    """Requested quantiles of an ensemble, without silently dropping draws."""

    levels: np.ndarray  # (Q,)
    world: np.ndarray  # (Q, Y)
    locations: np.ndarray  # (Q, Y, L)


@dataclass(frozen=True)
class ProjectionEnsemble:
    """Compact totals and complete provenance from probabilistic projections."""

    draw_ids: tuple[str, ...]
    years: np.ndarray  # (Y,)
    locations: tuple[str, ...]
    location_totals: np.ndarray  # (D, Y, L)
    draw_kind: str
    draw_weights: np.ndarray  # (D,), equal by construction for now
    draw_provenance: tuple[DrawProvenance, ...]
    base_population_revision: str
    base_population_source: str
    rate_extension: RateExtensionPolicy
    migration_source: str
    migration_independently_sourced: bool
    migration_scenario_knob: str | None
    migration_extension: SeriesExtension

    @property
    def n_draws(self) -> int:
        return len(self.draw_ids)

    @property
    def world(self) -> np.ndarray:
        """World population for every draw and year, shape ``(D, Y)``."""
        return self.location_totals.sum(axis=2)

    def quantiles(self, levels=(0.05, 0.5, 0.95)) -> ProjectionQuantiles:
        q = np.asarray(levels, dtype=np.float64)
        if q.ndim != 1 or len(q) == 0:
            raise ValueError("quantile levels must be a non-empty one-dimensional array")
        if not np.all(np.isfinite(q)) or np.any((q <= 0) | (q >= 1)):
            raise ValueError("quantile levels must be finite and strictly between 0 and 1")
        if len(np.unique(q)) != len(q):
            raise ValueError("quantile levels must not contain duplicates")
        return ProjectionQuantiles(
            levels=q,
            world=np.quantile(self.world, q, axis=0),
            locations=np.quantile(self.location_totals, q, axis=0),
        )


def _series_value(
    values: np.ndarray,
    index: int,
    *,
    year: int,
    component: str,
    extension: SeriesExtension,
) -> np.ndarray:
    if index < len(values):
        return values[index]
    if extension.mode == "hold-last":
        return values[-1]
    raise ValueError(
        f"{component} has no value for {year}; its extension policy requires source data"
    )


def propagate(
    base: BasePopulation,
    draws: Iterable[ProjectionDraw],
    *,
    end_year: int,
    migration: MigrationAssumption,
) -> ProjectionEnsemble:
    """Push paired prior or posterior draws through the engine one at a time."""

    if not isinstance(base, BasePopulation):
        raise TypeError("base must be BasePopulation")
    if not isinstance(migration, MigrationAssumption):
        raise TypeError("migration must be an explicit MigrationAssumption")

    iterator = iter(draws)
    try:
        first = next(iterator)
    except StopIteration as exc:
        raise ValueError("at least one projection draw is required") from exc
    if not isinstance(first, ProjectionDraw):
        raise TypeError("draws must yield ProjectionDraw objects")

    start_year = int(first.years[0])
    if start_year != base.year:
        raise ValueError("rate draws and base population must start in the same year")
    if int(end_year) != end_year or end_year <= start_year:
        raise ValueError(f"end_year must be after {start_year}")
    end_year = int(end_year)
    n_years = end_year - start_year

    if first.locations != base.locations:
        raise ValueError("draw locations do not match the base population")
    if migration.locations != first.locations:
        raise ValueError("migration locations do not match draw locations")
    if int(migration.years[0]) != start_year:
        raise ValueError("migration and rate draws must start in the same year")

    ids: list[str] = []
    provenance: list[DrawProvenance] = []
    weights: list[float] = []
    totals: list[np.ndarray] = []
    seen: set[str] = set()

    def run_one(draw: ProjectionDraw) -> None:
        if not isinstance(draw, ProjectionDraw):
            raise TypeError("draws must yield ProjectionDraw objects")
        if draw.draw_id in seen:
            raise ValueError(f"duplicate projection draw id {draw.draw_id!r}")
        if draw.locations != first.locations:
            raise ValueError(f"draw {draw.draw_id!r} has different locations")
        if not np.array_equal(draw.years, first.years):
            raise ValueError(f"draw {draw.draw_id!r} has different rate years")
        if draw.provenance.model_identity != first.provenance.model_identity:
            raise ValueError(f"draw {draw.draw_id!r} has different model provenance")
        if draw.draw_kind != first.draw_kind:
            raise ValueError(f"draw {draw.draw_id!r} has a different draw kind")
        if draw.weight != first.weight:
            raise ValueError(
                "nonuniform or reweighted draws are not supported yet; refusing "
                "to compute unweighted quantiles"
            )
        if draw.extension != first.extension:
            raise ValueError(f"draw {draw.draw_id!r} has a different rate extension policy")

        state = np.asarray(base.values, dtype=np.float64).copy()
        draw_totals = np.empty((n_years + 1, len(draw.locations)))
        draw_totals[0] = state.sum(axis=(1, 2))
        for index, year in enumerate(range(start_year, end_year)):
            sx = _series_value(
                draw.sx, index, year=year, component="mortality",
                extension=draw.extension.mortality,
            )
            asfr = _series_value(
                draw.asfr, index, year=year, component="fertility",
                extension=draw.extension.fertility,
            )
            srb = _series_value(
                draw.srb, index, year=year, component="sex ratio at birth",
                extension=draw.extension.sex_ratio,
            )
            mig = _series_value(
                migration.values, index, year=year, component="migration",
                extension=migration.extension,
            )
            state, _ = cohort.step(state, sx, asfr, srb, mig)
            draw_totals[index + 1] = state.sum(axis=(1, 2))

        seen.add(draw.draw_id)
        ids.append(draw.draw_id)
        provenance.append(draw.provenance)
        weights.append(draw.weight)
        totals.append(draw_totals)

    run_one(first)
    for draw in iterator:
        run_one(draw)

    ensemble_years = np.arange(start_year, end_year + 1)
    ensemble_years.setflags(write=False)
    location_totals = np.stack(totals)
    location_totals.setflags(write=False)
    draw_weights = np.asarray(weights)
    draw_weights.setflags(write=False)

    return ProjectionEnsemble(
        draw_ids=tuple(ids),
        years=ensemble_years,
        locations=first.locations,
        location_totals=location_totals,
        draw_kind=first.draw_kind,
        draw_weights=draw_weights,
        draw_provenance=tuple(provenance),
        base_population_revision=base.source_revision,
        base_population_source=base.source,
        rate_extension=first.extension,
        migration_source=migration.source,
        migration_independently_sourced=migration.independently_sourced,
        migration_scenario_knob=migration.scenario_knob,
        migration_extension=migration.extension,
    )

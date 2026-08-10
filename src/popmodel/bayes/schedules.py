"""Turn compact TFR and life-expectancy draws into engine-ready schedules.

UW publishes one number per country per year for fertility and two for
mortality. The cohort engine needs a hundred: births at every mother's age, and
survival at every age for each sex. Something has to fill that gap, and what
fills it is an assumption -- so it lives in its own separately versioned module
rather than hidden inside the source adapter or, worse, inside the engine.

The assumption, stated plainly
------------------------------
The UN's own age patterns are taken as given, and only their LEVEL is moved to
match the draw.

* **Fertility.** WPP 2024 publishes, for each country and year, how births are
  spread across mothers aged 10-54. That shape is normalised to sum to one and
  multiplied by the drawn total fertility rate. The drawn rate is therefore
  reproduced exactly, by construction, not approximately.
* **Mortality.** WPP 2024's survival ratios for the same country and year are
  the reference schedule. One number is added to that schedule on the logit
  scale, and solved so the schedule produces exactly the drawn life expectancy.
  This is Brass's relational method with the slope fixed at one.

What this claims, and what it does not
--------------------------------------
It does **not** claim to know how the age pattern of fertility or mortality
will change. It borrows the UN's view of that pattern for that country and
date, and moves only the level. Near the UN's own median the adjustment is
small and the age pattern is barely touched; far out in the tails the
adjustment is large and the relational assumption is doing real work.
:class:`ScheduleDiagnostics` reports how large the adjustment had to be, so
that can be judged rather than assumed.

This is a level-matching rule, not a fitted model. Nothing here is estimated
from the series it is meant to explain (standing instruction 1); the shift is
solved deterministically so that a stated input is reproduced.

Reading the mortality arithmetic
--------------------------------
``sx[a]`` is survival INTO age a -- read the header of ``engine/cohort.py``
before touching this. Chaining those ratios recovers the life table's
person-years column::

    P(a) = sx[0] * sx[1] * ... * sx[a] = L(a) / l(0)        for a = 0..99

and the open-ended group follows from the UN's ``sx[100] = T(100)/T(99)``::

    T(100) / l(0) = P(99) * sx[100] / (1 - sx[100])

Life expectancy at birth is the sum of the two. This was checked against WPP's
own published life expectancies before any of it was used: Finland 84.7892
against 84.7892, Japan 87.8785 against 87.8785, Nigeria 54.9390 against
54.9390. The survival ratios carry the whole life table, so a target life
expectancy can be hit exactly rather than approached.

A positive shift means better survival than the UN's schedule for that country
and year, and therefore a higher life expectancy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from popmodel.bayes.propagate import (
    DrawProvenance,
    ProjectionDraw,
    RateExtensionPolicy,
    TrajectoryDraw,
)
from popmodel.engine import cohort
from popmodel.ingest import wpp

CONVERTER_NAME = "wpp2024-relational"
CONVERTER_VERSION = "1.0.0"

#: Life expectancy is solved to this many years of the target. Far tighter than
#: anything demographically meaningful; the point is that failure to converge is
#: a bug, not a tolerance to be negotiated.
E0_TOLERANCE_YEARS = 1e-8

#: The widest logit shift the solver will consider. A shift of this size is
#: demographically absurd, so hitting the limit means the target is unreachable
#: from the reference schedule and the run should stop rather than approximate.
MAX_ABS_SHIFT = 20.0

#: Above this, the relational assumption is being asked to carry real weight and
#: the diagnostics say so out loud. Chosen as the point where the age pattern is
#: visibly redistributed rather than merely rescaled.
LARGE_SHIFT = 1.0


class ScheduleConversionError(RuntimeError):
    """A draw cannot be turned into engine inputs without inventing something."""


def _expit(y: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-y))


def _logit(p: np.ndarray) -> np.ndarray:
    if np.any((p <= 0.0) | (p >= 1.0)):
        raise ScheduleConversionError(
            "survival proportions must lie strictly between zero and one; a "
            "value of exactly zero or one has no logit and would mean nobody, "
            "or everybody, survives an entire year of age"
        )
    return np.log(p / (1.0 - p))


def life_years(sx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Person-years lived, per birth, from survival ratios.

    Args:
        sx: (..., 101) survival ratios in the UN's INTO-age-a sense.

    Returns:
        ``(P, open_group)`` where ``P`` is (..., 100) holding L(a)/l(0) for ages
        0-99, and ``open_group`` is (...) holding T(100)/l(0).
    """
    sx = np.asarray(sx, dtype=np.float64)
    if sx.shape[-1] != cohort.N_AGES:
        raise ScheduleConversionError(
            f"survival ratios must cover {cohort.N_AGES} ages; got {sx.shape[-1]}"
        )
    p = np.cumprod(sx[..., : cohort.MAX_AGE], axis=-1)
    top = sx[..., cohort.MAX_AGE]
    if np.any(top >= 1.0):
        raise ScheduleConversionError(
            "the open-ended survival ratio reached one, which would mean the "
            "100+ group never dies"
        )
    return p, p[..., -1] * top / (1.0 - top)


def life_expectancy(sx: np.ndarray) -> np.ndarray:
    """Life expectancy at birth implied by a schedule of survival ratios."""
    p, open_group = life_years(sx)
    return p.sum(axis=-1) + open_group


def _e0_from_shift(
    logit_p: np.ndarray, logit_top: np.ndarray, shift: np.ndarray
) -> np.ndarray:
    """Life expectancy after adding ``shift`` on the logit scale.

    Kept separate from :func:`shift_survival` because the solver evaluates this
    tens of times per schedule and does not need the survival ratios rebuilt
    each time.
    """
    p = _expit(logit_p + shift[..., None])
    top = _expit(logit_top + shift)
    return p.sum(axis=-1) + p[..., -1] * top / (1.0 - top)


def shift_survival(sx: np.ndarray, shift: np.ndarray) -> np.ndarray:
    """Move a survival schedule's level without changing its age pattern's shape.

    Args:
        sx: (..., 101) reference survival ratios.
        shift: (...) one logit shift per schedule. Positive means better
            survival than the reference.

    Returns:
        (..., 101) survival ratios, still in the UN's INTO-age-a sense.
    """
    sx = np.asarray(sx, dtype=np.float64)
    shift = np.asarray(shift, dtype=np.float64)
    if shift.shape != sx.shape[:-1]:
        raise ScheduleConversionError(
            f"need one shift per schedule: {sx.shape[:-1]} schedules, "
            f"{shift.shape} shifts"
        )

    p, _ = life_years(sx)
    moved = _expit(_logit(p) + shift[..., None])
    top = _expit(_logit(sx[..., cohort.MAX_AGE]) + shift)

    out = np.empty_like(sx)
    out[..., 0] = moved[..., 0]
    out[..., 1 : cohort.MAX_AGE] = moved[..., 1:] / moved[..., :-1]
    out[..., cohort.MAX_AGE] = top
    return out


def solve_shift(
    reference_sx: np.ndarray,
    target_e0: np.ndarray,
    *,
    tolerance: float = E0_TOLERANCE_YEARS,
) -> np.ndarray:
    """Find the logit shift that makes a reference schedule hit a target e0.

    Life expectancy increases strictly with the shift, so a bisection is
    guaranteed to converge once the target is bracketed. Vectorised: every
    schedule is solved at once.

    Raises:
        ScheduleConversionError: if a target lies outside what the reference
            schedule can reach within :data:`MAX_ABS_SHIFT`. Refusing is the
            right behaviour -- a silently clamped life expectancy is a wrong
            answer that looks like a right one.
    """
    reference_sx = np.asarray(reference_sx, dtype=np.float64)
    target = np.asarray(target_e0, dtype=np.float64)
    if target.shape != reference_sx.shape[:-1]:
        raise ScheduleConversionError(
            f"need one target per schedule: {reference_sx.shape[:-1]} schedules, "
            f"{target.shape} targets"
        )
    if not np.all(np.isfinite(target)) or np.any(target <= 0.0):
        raise ScheduleConversionError("target life expectancies must be positive")

    p, _ = life_years(reference_sx)
    logit_p = _logit(p)
    logit_top = _logit(reference_sx[..., cohort.MAX_AGE])

    lo = np.full(target.shape, -MAX_ABS_SHIFT)
    hi = np.full(target.shape, MAX_ABS_SHIFT)
    e0_lo = _e0_from_shift(logit_p, logit_top, lo)
    e0_hi = _e0_from_shift(logit_p, logit_top, hi)
    unreachable = (target < e0_lo) | (target > e0_hi)
    if np.any(unreachable):
        worst = int(np.argmax(unreachable.ravel()))
        raise ScheduleConversionError(
            f"{int(unreachable.sum())} target life expectanc(ies) cannot be "
            f"reached from the reference schedule within a logit shift of "
            f"{MAX_ABS_SHIFT}; the first is {target.ravel()[worst]:.3f} years "
            f"against a reachable range of {e0_lo.ravel()[worst]:.3f} to "
            f"{e0_hi.ravel()[worst]:.3f}"
        )

    # Bracket width 40 halved to below 1e-12 takes about 55 steps; the cap is
    # generous and the loop exits on the tolerance long before reaching it.
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        e0_mid = _e0_from_shift(logit_p, logit_top, mid)
        if np.max(np.abs(e0_mid - target)) <= tolerance:
            return mid
        too_low = e0_mid < target
        lo = np.where(too_low, mid, lo)
        hi = np.where(too_low, hi, mid)

    raise ScheduleConversionError(
        "the life-expectancy solver did not converge; this is a bug, not a "
        "tolerance to widen"
    )


def scale_fertility(reference_asfr: np.ndarray, target_tfr: np.ndarray) -> np.ndarray:
    """Spread a total fertility rate over ages using a reference age pattern.

    The total fertility rate is the sum of the single-age rates, so rescaling a
    reference schedule to a new sum reproduces the target exactly.
    """
    reference_asfr = np.asarray(reference_asfr, dtype=np.float64)
    target = np.asarray(target_tfr, dtype=np.float64)
    if target.shape != reference_asfr.shape[:-1]:
        raise ScheduleConversionError(
            f"need one total fertility rate per schedule: "
            f"{reference_asfr.shape[:-1]} schedules, {target.shape} targets"
        )
    if np.any(target < 0.0) or not np.all(np.isfinite(target)):
        raise ScheduleConversionError("target fertility must be finite and non-negative")

    reference_total = reference_asfr.sum(axis=-1)
    if np.any(reference_total <= 0.0):
        raise ScheduleConversionError(
            "a reference country-year has no births at any age, so it carries no "
            "age pattern to borrow"
        )
    return reference_asfr * (target / reference_total)[..., None]


@dataclass(frozen=True)
class ScheduleDiagnostics:
    """How hard the relational assumption had to work for one draw.

    Small shifts mean the draw sits near the UN's own schedule and the borrowed
    age pattern is close to untouched. Large ones mean the age pattern is being
    materially redistributed, which is a modelling claim and should be read as
    one.
    """

    draw_id: str
    max_abs_shift: float
    mean_abs_shift: float
    share_above_large_shift: float
    max_fertility_ratio: float
    min_fertility_ratio: float

    def summary(self) -> str:
        return (
            f"{self.draw_id}: mortality shift |max| {self.max_abs_shift:.3f}, "
            f"mean {self.mean_abs_shift:.3f}, "
            f"{self.share_above_large_shift:.1%} above {LARGE_SHIFT}; "
            f"fertility scaled {self.min_fertility_ratio:.3f}-"
            f"{self.max_fertility_ratio:.3f}x"
        )


@dataclass(frozen=True)
class ReferenceSchedules:
    """The UN age patterns this converter borrows, indexed for fast lookup."""

    revision: str
    years: np.ndarray
    locations: tuple[str, ...]
    asfr: np.ndarray  # (T, L, 101)
    sx: np.ndarray  # (T, L, 2, 101)
    srb: np.ndarray  # (T, L)

    @classmethod
    def from_bundle(cls, bundle=None) -> "ReferenceSchedules":
        bundle = bundle if bundle is not None else wpp.load_bundle()
        return cls(
            revision=str(bundle.provenance["revision_label"]),
            years=np.asarray(bundle.years, dtype=np.int64),
            locations=tuple(str(code) for code in bundle.iso3),
            asfr=np.asarray(bundle.asfr, dtype=np.float64),
            sx=np.asarray(bundle.sx, dtype=np.float64),
            srb=np.asarray(bundle.srb, dtype=np.float64),
        )

    def select(
        self, years: np.ndarray, locations: tuple[str, ...]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Reference arrays for exactly these years and countries, in order.

        Raises on anything it cannot match. A draw quietly aligned to the wrong
        year or a missing country is precisely the failure standing instruction
        5 exists to prevent.
        """
        index = {code: i for i, code in enumerate(self.locations)}
        missing = [code for code in locations if code not in index]
        if missing:
            raise ScheduleConversionError(
                f"no WPP reference schedule for {len(missing)} location(s): "
                f"{', '.join(missing[:5])}"
            )
        columns = np.array([index[code] for code in locations], dtype=np.int64)

        first = int(self.years[0])
        rows = np.asarray(years, dtype=np.int64) - first
        if np.any(rows < 0) or np.any(rows >= len(self.years)):
            raise ScheduleConversionError(
                f"draw years {int(years[0])}-{int(years[-1])} fall outside the "
                f"WPP reference range {first}-{int(self.years[-1])}"
            )

        return (
            self.asfr[np.ix_(rows, columns)],
            self.sx[np.ix_(rows, columns)],
            self.srb[np.ix_(rows, columns)],
        )


class WppRelationalConverter:
    """A :class:`ScheduleConverter`: WPP age patterns, drawn levels.

    Args:
        extension: what the engine should do for projected years beyond the end
            of the draw. UW stops at 2100 and this project runs to 2150, so
            those fifty years are an assumption of ours and the caller is made
            to state it.
        reference: the WPP schedules to borrow. Loaded from the built bundle if
            not supplied.
    """

    name = CONVERTER_NAME
    version = CONVERTER_VERSION

    def __init__(
        self,
        *,
        extension: RateExtensionPolicy,
        reference: ReferenceSchedules | None = None,
    ) -> None:
        if not isinstance(extension, RateExtensionPolicy):
            raise TypeError("extension must be an explicit RateExtensionPolicy")
        self.extension = extension
        self.reference = reference or ReferenceSchedules.from_bundle()
        self._last_diagnostics: ScheduleDiagnostics | None = None

    @property
    def rate_conversion(self) -> str:
        """The provenance string that travels with every converted draw."""
        return (
            f"{self.name} {self.version}: age patterns borrowed from "
            f"{self.reference.revision} for the same country and year; total "
            f"fertility reproduced exactly by rescaling the age pattern; life "
            f"expectancy reproduced exactly by a single Brass logit shift of "
            f"the survival schedule, slope fixed at one; sex ratio at birth "
            f"taken from the same reference unchanged"
        )

    @property
    def last_diagnostics(self) -> ScheduleDiagnostics | None:
        """Diagnostics for the most recently converted draw."""
        return self._last_diagnostics

    def convert(self, draw: TrajectoryDraw) -> ProjectionDraw:
        if not isinstance(draw, TrajectoryDraw):
            raise TypeError("convert expects a TrajectoryDraw")

        asfr_ref, sx_ref, srb_ref = self.reference.select(draw.years, draw.locations)

        asfr = scale_fertility(asfr_ref, draw.tfr)

        target_e0 = np.stack([draw.e0_female, draw.e0_male], axis=-1)  # (T, L, 2)
        shift = solve_shift(sx_ref, target_e0)
        sx = shift_survival(sx_ref, shift)

        reference_tfr = asfr_ref.sum(axis=-1)
        ratio = draw.tfr / reference_tfr
        absolute = np.abs(shift)
        self._last_diagnostics = ScheduleDiagnostics(
            draw_id=draw.draw_id,
            max_abs_shift=float(absolute.max()),
            mean_abs_shift=float(absolute.mean()),
            share_above_large_shift=float((absolute > LARGE_SHIFT).mean()),
            max_fertility_ratio=float(ratio.max()),
            min_fertility_ratio=float(ratio.min()),
        )

        provenance = DrawProvenance(
            source_revision=draw.provenance.source_revision,
            fertility_source=draw.provenance.fertility_source,
            mortality_source=draw.provenance.mortality_source,
            fertility_draw_id=draw.provenance.fertility_draw_id,
            mortality_draw_id=draw.provenance.mortality_draw_id,
            coupling_method=draw.provenance.coupling_method,
            rate_conversion=self.rate_conversion,
        )

        return ProjectionDraw(
            draw_id=draw.draw_id,
            years=draw.years,
            locations=draw.locations,
            sx=sx,
            asfr=asfr,
            srb=srb_ref,
            draw_kind=draw.draw_kind,
            weight=draw.weight,
            provenance=provenance,
            extension=self.extension,
        )

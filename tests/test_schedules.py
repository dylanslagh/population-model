"""Tests for the TFR/e0-to-age-schedule converter.

These run without any downloaded data. The reference schedules are built by
hand so the arithmetic is checked against something independently known rather
than against whatever the bundle happens to contain.
"""

from __future__ import annotations

import numpy as np
import pytest

from popmodel.bayes import (
    RateExtensionPolicy,
    TrajectoryDraw,
    TrajectoryProvenance,
)
from popmodel.bayes import schedules as sched
from popmodel.engine import cohort


def make_sx(level: float = 0.99) -> np.ndarray:
    """A crude but valid survival schedule: constant hazard, thinner at the top."""
    sx = np.full(cohort.N_AGES, level)
    sx[0] = 0.995
    sx[90:] = np.linspace(level, 0.6, cohort.N_AGES - 90)
    return sx


def make_asfr(total: float = 2.0) -> np.ndarray:
    asfr = np.zeros(cohort.N_AGES)
    ages = np.arange(cohort.FERT_AGE_MIN, cohort.FERT_AGE_MAX + 1)
    bell = np.exp(-0.5 * ((ages - 28) / 6.0) ** 2)
    asfr[cohort.FERT_AGE_MIN : cohort.FERT_AGE_MAX + 1] = bell / bell.sum() * total
    return asfr


def make_reference(years=(2024, 2025), locations=("AAA", "BBB")):
    t, n = len(years), len(locations)
    asfr = np.zeros((t, n, cohort.N_AGES))
    sx = np.zeros((t, n, cohort.N_SEXES, cohort.N_AGES))
    for i in range(t):
        for j in range(n):
            asfr[i, j] = make_asfr(1.8 + 0.1 * j)
            sx[i, j, cohort.FEMALE] = make_sx(0.990 + 0.001 * j)
            sx[i, j, cohort.MALE] = make_sx(0.988 + 0.001 * j)
    return sched.ReferenceSchedules(
        revision="test reference",
        years=np.array(years, dtype=np.int64),
        locations=tuple(locations),
        asfr=asfr,
        sx=sx,
        srb=np.full((t, n), 1.05),
    )


def make_draw(reference, tfr=1.5, e0f=80.0, e0m=75.0, draw_id="draw-1"):
    t, n = len(reference.years), len(reference.locations)
    provenance = TrajectoryProvenance(
        source_revision="test",
        fertility_source="test fertility",
        mortality_source="test mortality",
        fertility_draw_id="f-1",
        mortality_draw_id="m-1",
        coupling_method="paired by index for the test",
    )
    return TrajectoryDraw(
        draw_id=draw_id,
        years=reference.years,
        locations=reference.locations,
        tfr=np.full((t, n), tfr),
        e0_female=np.full((t, n), e0f),
        e0_male=np.full((t, n), e0m),
        draw_kind="posterior",
        weight=1.0,
        provenance=provenance,
    )


# --- life expectancy from survival ratios ------------------------------------


def test_life_expectancy_matches_a_hand_computed_life_table():
    """The one piece of arithmetic everything else rests on.

    Built from an explicit life table rather than from survival ratios, so the
    test knows the answer before the code does.
    """
    rng = np.random.default_rng(0)
    hazard = np.clip(rng.uniform(0.001, 0.05, cohort.N_AGES), 0.001, 0.2)
    lx = np.concatenate([[1.0], np.cumprod(1.0 - hazard)])  # l(0)..l(101)
    Lx = 0.5 * (lx[:-1] + lx[1:])  # person-years in each single year

    sx = np.empty(cohort.N_AGES)
    sx[0] = Lx[0] / lx[0]
    sx[1 : cohort.MAX_AGE] = Lx[1 : cohort.MAX_AGE] / Lx[0 : cohort.MAX_AGE - 1]
    T100 = Lx[cohort.MAX_AGE :].sum()
    T99 = Lx[cohort.MAX_AGE - 1] + T100
    sx[cohort.MAX_AGE] = T100 / T99

    expected = (Lx[: cohort.MAX_AGE].sum() + T100) / lx[0]
    assert sched.life_expectancy(sx) == pytest.approx(expected, abs=1e-12)


def test_life_years_splits_into_closed_ages_and_the_open_group():
    sx = make_sx()
    p, open_group = sched.life_years(sx)
    assert p.shape == (cohort.MAX_AGE,)
    assert p[0] == pytest.approx(sx[0])
    assert p[1] == pytest.approx(sx[0] * sx[1])
    assert np.all(np.diff(p) < 0)  # a survivorship curve only goes down
    assert open_group > 0
    assert sched.life_expectancy(sx) == pytest.approx(p.sum() + open_group)


def test_life_years_rejects_a_deathless_open_group():
    sx = make_sx()
    sx[cohort.MAX_AGE] = 1.0
    with pytest.raises(sched.ScheduleConversionError, match="never dies"):
        sched.life_years(sx)


# --- the mortality level shift ------------------------------------------------


def test_zero_shift_changes_nothing():
    sx = make_sx()
    assert sched.shift_survival(sx, np.array(0.0)) == pytest.approx(sx, abs=1e-15)


def test_solving_for_a_schedules_own_life_expectancy_returns_no_shift():
    """The identity case. If this drifts, every draw is quietly biased."""
    sx = np.stack([make_sx(0.99), make_sx(0.985)])
    shift = sched.solve_shift(sx, sched.life_expectancy(sx))
    assert np.abs(shift).max() < 1e-9
    assert sched.shift_survival(sx, shift) == pytest.approx(sx, abs=1e-12)


@pytest.mark.parametrize("target", [60.0, 70.0, 82.5, 95.0])
def test_the_solver_hits_its_target_life_expectancy(target):
    sx = make_sx()
    shift = sched.solve_shift(sx, np.array(target))
    produced = sched.life_expectancy(sched.shift_survival(sx, shift))
    assert produced == pytest.approx(target, abs=1e-6)


def test_a_positive_shift_means_better_survival():
    sx = make_sx()
    base = sched.life_expectancy(sx)
    assert sched.life_expectancy(sched.shift_survival(sx, np.array(0.5))) > base
    assert sched.life_expectancy(sched.shift_survival(sx, np.array(-0.5))) < base


def test_shifted_schedules_stay_valid_survival_ratios():
    sx = make_sx()
    for shift in (-3.0, -1.0, 1.0, 3.0):
        moved = sched.shift_survival(sx, np.array(shift))
        assert np.all(moved > 0.0) and np.all(moved <= 1.0)


def test_an_unreachable_life_expectancy_raises_rather_than_clamping():
    sx = make_sx()
    with pytest.raises(sched.ScheduleConversionError, match="cannot be reached"):
        sched.solve_shift(sx, np.array(1e-6))


def test_the_solver_needs_one_target_per_schedule():
    sx = np.stack([make_sx(), make_sx()])
    with pytest.raises(sched.ScheduleConversionError, match="one target per schedule"):
        sched.solve_shift(sx, np.array([80.0, 80.0, 80.0]))


# --- the fertility rescale ----------------------------------------------------


def test_rescaled_fertility_reproduces_the_target_total_exactly():
    asfr = np.stack([make_asfr(2.1), make_asfr(4.0)])
    target = np.array([1.3, 3.7])
    out = sched.scale_fertility(asfr, target)
    assert out.sum(axis=-1) == pytest.approx(target, abs=1e-13)


def test_rescaling_preserves_the_age_pattern():
    asfr = make_asfr(2.1)
    out = sched.scale_fertility(asfr, np.array(1.2))
    shape_in = asfr / asfr.sum()
    shape_out = out / out.sum()
    assert shape_out == pytest.approx(shape_in, abs=1e-14)


def test_rescaling_keeps_births_inside_the_childbearing_ages():
    out = sched.scale_fertility(make_asfr(2.0), np.array(6.0))
    assert out[: cohort.FERT_AGE_MIN].sum() == 0.0
    assert out[cohort.FERT_AGE_MAX + 1 :].sum() == 0.0


def test_a_reference_with_no_births_has_no_age_pattern_to_borrow():
    with pytest.raises(sched.ScheduleConversionError, match="no births"):
        sched.scale_fertility(np.zeros(cohort.N_AGES), np.array(2.0))


# --- the converter as a whole -------------------------------------------------


def test_convert_reproduces_both_source_quantities():
    reference = make_reference()
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    draw = make_draw(reference, tfr=1.42, e0f=83.5, e0m=78.25)
    projection = converter.convert(draw)

    assert projection.asfr.sum(axis=-1) == pytest.approx(draw.tfr, abs=1e-12)
    produced = sched.life_expectancy(projection.sx)
    assert produced[..., cohort.FEMALE] == pytest.approx(draw.e0_female, abs=1e-6)
    assert produced[..., cohort.MALE] == pytest.approx(draw.e0_male, abs=1e-6)


def test_convert_carries_the_source_provenance_and_names_the_conversion():
    reference = make_reference()
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    projection = converter.convert(make_draw(reference))

    assert projection.provenance.fertility_draw_id == "f-1"
    assert projection.provenance.mortality_draw_id == "m-1"
    assert "paired by index" in projection.provenance.coupling_method
    assert converter.version in projection.provenance.rate_conversion
    assert "test reference" in projection.provenance.rate_conversion


def test_convert_reports_how_far_it_moved_the_reference():
    reference = make_reference()
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    converter.convert(make_draw(reference, tfr=0.9))
    small = converter.last_diagnostics
    converter.convert(make_draw(reference, tfr=0.9, e0f=97.0, e0m=96.0))
    large = converter.last_diagnostics

    assert large.max_abs_shift > small.max_abs_shift
    assert 0.0 < small.min_fertility_ratio < 1.0
    assert "mortality shift" in small.summary()


def test_convert_refuses_a_country_with_no_reference_schedule():
    reference = make_reference()
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    draw = make_draw(reference)
    stranger = TrajectoryDraw(
        draw_id=draw.draw_id,
        years=draw.years,
        locations=("AAA", "ZZZ"),
        tfr=draw.tfr,
        e0_female=draw.e0_female,
        e0_male=draw.e0_male,
        draw_kind=draw.draw_kind,
        weight=draw.weight,
        provenance=draw.provenance,
    )
    with pytest.raises(sched.ScheduleConversionError, match="ZZZ"):
        converter.convert(stranger)


def test_convert_refuses_years_outside_the_reference():
    reference = make_reference(years=(2024, 2025))
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    draw = make_draw(reference)
    later = TrajectoryDraw(
        draw_id=draw.draw_id,
        years=np.array([2100, 2101]),
        locations=draw.locations,
        tfr=draw.tfr,
        e0_female=draw.e0_female,
        e0_male=draw.e0_male,
        draw_kind=draw.draw_kind,
        weight=draw.weight,
        provenance=draw.provenance,
    )
    with pytest.raises(sched.ScheduleConversionError, match="outside"):
        converter.convert(later)


def test_the_extension_policy_must_be_stated():
    with pytest.raises(TypeError, match="explicit RateExtensionPolicy"):
        sched.WppRelationalConverter(extension="hold-last", reference=make_reference())


def test_converted_draws_are_accepted_by_the_engine():
    """The real contract: what comes out must run through the cohort step."""
    reference = make_reference()
    converter = sched.WppRelationalConverter(
        extension=RateExtensionPolicy.strict(), reference=reference
    )
    projection = converter.convert(make_draw(reference))

    pop = np.full((len(reference.locations), cohort.N_SEXES, cohort.N_AGES), 1000.0)
    nxt, births = cohort.step(
        pop, projection.sx[0], projection.asfr[0], projection.srb[0]
    )
    assert np.all(np.isfinite(nxt)) and np.all(nxt >= 0)
    assert np.all(births > 0)

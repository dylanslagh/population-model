"""Phase 4's two-stage boundary, checked on arithmetic small enough to inspect."""

from __future__ import annotations

import numpy as np
import pytest

from popmodel.bayes import (
    BasePopulation,
    DrawProvenance,
    MigrationAssumption,
    ProjectionDraw,
    RateExtensionPolicy,
    SeriesExtension,
    TrajectoryDraw,
    TrajectoryProvenance,
    propagate,
)
from popmodel.engine import cohort


def provenance(draw_id="1", *, coupling="paired synthetic components by test index"):
    return DrawProvenance(
        source_revision="synthetic-v1",
        fertility_source="made-up rates with an answer worked out by hand",
        mortality_source="made-up survival with an answer worked out by hand",
        fertility_draw_id=f"fertility-{draw_id}",
        mortality_draw_id=f"mortality-{draw_id}",
        coupling_method=coupling,
        rate_conversion="already expressed as age-specific engine inputs",
    )


def make_draw(
    draw_id="draw-1", *, years=(2000,), locations=("AAA",), fertility=0.0,
    survival=1.0, extension=None, provenance_value=None, draw_kind="posterior",
    weight=1.0,
):
    t, loc = len(years), len(locations)
    sx = np.full((t, loc, cohort.N_SEXES, cohort.N_AGES), survival)
    asfr = np.zeros((t, loc, cohort.N_AGES))
    asfr[..., 20] = fertility
    srb = np.ones((t, loc))
    return ProjectionDraw(
        draw_id=draw_id,
        years=np.asarray(years),
        locations=locations,
        sx=sx,
        asfr=asfr,
        srb=srb,
        draw_kind=draw_kind,
        weight=weight,
        provenance=provenance_value or provenance(draw_id),
        extension=extension or RateExtensionPolicy.strict(),
    )


def base_population(locations=("AAA",)):
    pop = np.zeros((len(locations), cohort.N_SEXES, cohort.N_AGES))
    pop[:, :, 20] = 1000.0
    return BasePopulation(
        year=2000,
        locations=locations,
        values=pop,
        source_revision="synthetic-v1",
        source="made-up 1 January population for a unit test",
    )


def zero_migration(end_year=2001, locations=("AAA",)):
    return MigrationAssumption.zero(np.arange(2000, end_year), locations)


def test_one_posterior_draw_is_exactly_the_deterministic_run():
    draw = make_draw(years=(2000, 2001, 2002), fertility=0.05, survival=0.98)
    ensemble = propagate(
        base_population(), [draw], end_year=2003, migration=zero_migration(2003)
    )
    expected = cohort.project(
        base_population().values, start_year=2000, sx=draw.sx, asfr=draw.asfr,
        srb=draw.srb, migration=zero_migration(2003).values, n_years=3,
    )
    assert ensemble.draw_ids == ("draw-1",)
    assert np.array_equal(ensemble.years, expected.years)
    assert np.allclose(ensemble.location_totals[0], expected.location_totals())
    assert np.allclose(ensemble.world[0], expected.world)
    assert ensemble.base_population_revision == "synthetic-v1"


def test_joint_draws_remain_separate_and_component_ids_are_preserved():
    low = make_draw("low", fertility=0.0)
    high = make_draw("high", fertility=0.2)
    ensemble = propagate(
        base_population(), (d for d in (low, high)), end_year=2001,
        migration=zero_migration(),
    )

    # Starting with 1,000 women and 1,000 men aged 20: no-fertility stays at
    # 2,000, while rate 0.2 acts on 500 mid-year women and adds 100 babies.
    assert ensemble.world[:, -1].tolist() == pytest.approx([2000.0, 2100.0])
    assert [p.fertility_draw_id for p in ensemble.draw_provenance] == [
        "fertility-low", "fertility-high"
    ]
    assert [p.mortality_draw_id for p in ensemble.draw_provenance] == [
        "mortality-low", "mortality-high"
    ]
    q = ensemble.quantiles((0.25, 0.5, 0.75))
    assert q.world[:, -1].tolist() == pytest.approx([2025.0, 2050.0, 2075.0])
    assert q.locations.shape == (3, 2, 1)


def test_rates_do_not_silently_extend_past_their_source():
    draw = make_draw(survival=0.5)
    with pytest.raises(ValueError, match="mortality has no value for 2001"):
        propagate(
            base_population(), [draw], end_year=2003,
            migration=zero_migration(2003),
        )

    held = make_draw(
        survival=0.5,
        extension=RateExtensionPolicy.hold_all(
            "deliberate test assumption: freeze the final supplied rate"
        ),
    )
    ensemble = propagate(
        base_population(), [held], end_year=2003,
        migration=zero_migration(2003),
    )
    assert ensemble.world[0, -1] == pytest.approx(2000.0 * 0.5**3)
    assert ensemble.rate_extension.mortality.mode == "hold-last"


def test_draw_contract_rejects_failures_that_would_look_plausible():
    with pytest.raises(ValueError, match="consecutive"):
        make_draw(years=(2000, 2002))
    with pytest.raises(ValueError, match="between zero and one"):
        make_draw(survival=1.01)

    good = make_draw()
    outside = good.asfr.copy()
    outside[..., 5] = 0.1
    with pytest.raises(ValueError, match="outside ages"):
        ProjectionDraw(
            "bad ages", good.years, good.locations, good.sx, outside, good.srb,
            good.draw_kind, good.weight, good.provenance, good.extension,
        )


def test_base_population_rejects_negative_or_untraceable_people():
    pop = base_population().values.copy()
    pop[0, 0, 20] = -1
    with pytest.raises(ValueError, match="negative people"):
        BasePopulation(2000, ("AAA",), pop, "synthetic-v1", "unit test")
    with pytest.raises(ValueError, match="source must be stated"):
        BasePopulation(2000, ("AAA",), np.zeros_like(pop), "synthetic-v1", "")


def test_validated_arrays_cannot_change_behind_their_provenance():
    base = base_population()
    draw = make_draw()
    migration = zero_migration()
    for values in (base.values, draw.years, draw.sx, draw.asfr, draw.srb,
                   migration.values):
        assert not values.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            values.flat[0] = values.flat[0]

    ensemble = propagate(base, [draw], end_year=2001, migration=migration)
    assert not ensemble.location_totals.flags.writeable
    assert not ensemble.draw_weights.flags.writeable


def test_an_ensemble_cannot_mix_incompatible_draws_or_coupling_rules():
    first = make_draw("first")
    other_locations = make_draw("second", locations=("BBB",))
    with pytest.raises(ValueError, match="different locations"):
        propagate(
            base_population(), [first, other_locations], end_year=2001,
            migration=zero_migration(),
        )

    duplicate = make_draw("first")
    with pytest.raises(ValueError, match="duplicate projection draw id"):
        propagate(
            base_population(), [first, duplicate], end_year=2001,
            migration=zero_migration(),
        )

    differently_coupled = make_draw(
        "second", provenance_value=provenance("second", coupling="random permutation")
    )
    with pytest.raises(ValueError, match="different model provenance"):
        propagate(
            base_population(), [first, differently_coupled], end_year=2001,
            migration=zero_migration(),
        )

    prior = make_draw("prior", draw_kind="prior")
    with pytest.raises(ValueError, match="different draw kind"):
        propagate(
            base_population(), [first, prior], end_year=2001,
            migration=zero_migration(),
        )

    reweighted = make_draw("weighted", weight=0.5)
    with pytest.raises(ValueError, match="reweighted draws"):
        propagate(
            base_population(), [first, reweighted], end_year=2001,
            migration=zero_migration(),
        )


def test_prior_draws_use_the_same_required_propagation_path():
    ensemble = propagate(
        base_population(), [make_draw(draw_kind="prior")], end_year=2001,
        migration=zero_migration(),
    )
    assert ensemble.draw_kind == "prior"
    assert ensemble.draw_weights.tolist() == [1.0]


def test_compact_trajectory_draw_is_not_confused_with_engine_rates():
    source = TrajectoryProvenance(
        source_revision="UW WPP2024-aligned annual trajectories",
        fertility_source="UW annual TFR archive; manifest key tfr_annual",
        mortality_source="UW annual e0 archive; manifest key e0_annual",
        fertility_draw_id="trajectory-17",
        mortality_draw_id="trajectory-42",
        coupling_method="explicit test pairing; not claimed as a joint posterior",
    )
    draw = TrajectoryDraw(
        draw_id="paired-1",
        years=np.array([2024, 2025]),
        locations=("AAA", "BBB"),
        tfr=np.array([[1.2, 3.1], [1.3, 3.0]]),
        e0_female=np.array([[84.0, 70.0], [84.2, 70.3]]),
        e0_male=np.array([[79.0, 66.0], [79.2, 66.3]]),
        draw_kind="posterior",
        weight=1.0,
        provenance=source,
    )
    assert draw.tfr.shape == (2, 2)
    assert draw.provenance.fertility_draw_id == "trajectory-17"
    assert "not claimed" in draw.provenance.coupling_method


def test_compact_trajectories_fail_on_missing_or_impossible_values():
    source = TrajectoryProvenance(
        "test", "fertility", "mortality", "f-1", "m-1", "paired by test index"
    )
    with pytest.raises(ValueError, match="e0_male must be"):
        TrajectoryDraw(
            "bad shape", np.array([2024]), ("AAA",), np.ones((1, 1)),
            np.ones((1, 1)), np.ones((2, 1)), "posterior", 1.0, source,
        )
    with pytest.raises(ValueError, match="e0_female must be positive"):
        TrajectoryDraw(
            "bad e0", np.array([2024]), ("AAA",), np.ones((1, 1)),
            np.zeros((1, 1)), np.ones((1, 1)), "posterior", 1.0, source,
        )


def test_migration_is_mandatory_and_non_independent_paths_are_labelled():
    with pytest.raises(TypeError, match="explicit MigrationAssumption"):
        propagate(base_population(), [make_draw()], end_year=2001, migration=None)

    values = np.zeros((1, 1, cohort.N_SEXES, cohort.N_AGES))
    with pytest.raises(ValueError, match="scenario knob"):
        MigrationAssumption(
            years=np.array([2000]), locations=("AAA",), values=values,
            source="backed out of a fitted population path", independently_sourced=False,
            extension=SeriesExtension.require_source(),
        )

    migration = MigrationAssumption(
        years=np.array([2000]), locations=("AAA",), values=values,
        source="backed out of a fitted population path", independently_sourced=False,
        extension=SeriesExtension.require_source(),
        scenario_knob="net migration by age (residual, not independently sourced)",
    )
    ensemble = propagate(
        base_population(), [make_draw()], end_year=2001, migration=migration
    )
    assert ensemble.migration_source == migration.source
    assert ensemble.migration_scenario_knob == migration.scenario_knob


def test_quantile_levels_are_checked():
    ensemble = propagate(
        base_population(), [make_draw()], end_year=2001,
        migration=zero_migration(),
    )
    with pytest.raises(ValueError, match="between 0 and 1"):
        ensemble.quantiles((0.0, 0.5))
    with pytest.raises(ValueError, match="duplicates"):
        ensemble.quantiles((0.5, 0.5))

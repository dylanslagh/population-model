"""Posterior draws in, deterministic demographic projections out.

The sampler never imports the cohort engine. Stage 1 produces complete rate
draws; stage 2, implemented here, sends those draws through the engine one at a
time. Keeping that boundary explicit is the central Phase 4 architecture rule.
"""

from popmodel.bayes.propagate import (  # noqa: F401
    BasePopulation,
    DrawProvenance,
    MigrationAssumption,
    ProjectionDraw,
    ProjectionDrawSource,
    ProjectionEnsemble,
    ProjectionQuantiles,
    RateExtensionPolicy,
    ScheduleConverter,
    SeriesExtension,
    TrajectoryDraw,
    TrajectoryDrawSource,
    TrajectoryProvenance,
    propagate,
)

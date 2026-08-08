"""The deterministic projection engine.

Spec section 5.2. Plain English: one very large spreadsheet with a row for every
country, age and sex, and a rule for moving people through it one year at a
time. Programmers call it a Leslie-matrix projection. The important property is
what is NOT in here:

    This module contains no theory about future fertility.

It takes fertility, mortality and migration as given and does the bookkeeping.
Every hypothesis the project actually cares about lives upstream of this file,
in whatever produced those inputs. If a mechanism ever leaks in here, the
project loses the ability to say which of its results came from a mechanism and
which came from arithmetic.

Conventions, stated once
------------------------
* Ages are single years, 0 to 100, where 100 means "100 and over".
* Sex index 0 is female, 1 is male. Female first, because fertility needs it.
* Populations are counts of people on 1 January. One step carries 1 Jan of year
  t to 1 Jan of year t+1, and the rates supplied for step t are the ones in
  force during calendar year t.
* Populations are PEOPLE, not thousands. WPP publishes thousands; the ingest
  layer multiplies by 1000 exactly once, and nothing downstream has to wonder.

Survival ratios: read this bit twice
------------------------------------
`sx[a]` is the survival ratio INTO age a, not out of it. This is the UN's own
convention (the Sx column of the WPP life tables) and it is adopted here
deliberately, so that the numbers in this engine are the numbers in the source
file with no translation step in between. Translation steps are where sign and
off-by-one errors live.

    sx[0]      share of the year's babies still alive on 1 January following.
               It is L(0)/l(0) from the life table, not p(0): a baby born in
               July is only exposed for half a year.
    sx[a]      for 1..99: share of people aged a-1 on 1 January who are alive
               and aged a a year later.
    sx[100]    the open-ended group. Applies to the SUM of the 99-year-olds and
               the existing 100+ group, because both end up in 100+. It is
               T(100)/T(99): person-years lived above age 100, over person-years
               lived above age 99.

The one arithmetic subtlety
---------------------------
Age-specific fertility rates are births to women aged a divided by the MID-year
number of women aged a. So the count of women used here is the average of the 1
January figure and the following 1 January figure, not the starting figure.
Getting this wrong biases births by roughly half a year of cohort change: small
in any one year, and very much not small after 126 of them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAX_AGE = 100  # top bucket is open-ended: 100+
N_AGES = MAX_AGE + 1
FEMALE, MALE = 0, 1
N_SEXES = 2

# Childbearing ages. Note this is 10-54, not the 15-49 of WPP's single-age
# fertility file: mothers under 15 and over 49 are about 0.3% of world births,
# which is nothing in one year and a visible bias after 126 of them.
FERT_AGE_MIN = 10
FERT_AGE_MAX = 54


@dataclass
class ProjectionResult:
    """What a run produces. Populations are at 1 January of each year."""

    years: np.ndarray  # (T+1,) int
    population: np.ndarray  # (T+1, L, 2, 101) people
    births: np.ndarray  # (T, L) births during each calendar year
    deaths: np.ndarray  # (T, L) implied deaths during each calendar year
    locations: list[str]  # length L, ISO3 codes

    @property
    def world(self) -> np.ndarray:
        """(T+1,) world population at each 1 January."""
        return self.population.sum(axis=(1, 2, 3))

    def location_totals(self) -> np.ndarray:
        """(T+1, L) total population per country per year."""
        return self.population.sum(axis=(2, 3))

    def pyramid(self, code: str) -> np.ndarray:
        """(T+1, 2, 101) one country's pyramids through time."""
        return self.population[:, self.locations.index(code)]

    def year_index(self, year: int) -> int:
        idx = int(year - self.years[0])
        if not 0 <= idx < len(self.years):
            raise KeyError(f"{year} is outside {self.years[0]}-{self.years[-1]}")
        return idx


def step(
    pop: np.ndarray,
    sx: np.ndarray,
    asfr: np.ndarray,
    srb: np.ndarray,
    migration: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Advance one year. Vectorised over countries.

    Args:
        pop: (L, 2, 101) population on 1 January.
        sx: (L, 2, 101) survival ratios, in the INTO-age-a sense above.
        asfr: (L, 101) births per woman per year by age; zero outside
            childbearing ages.
        srb: (L,) sex ratio at birth, male births per female birth.
        migration: (L, 2, 101) net migrants during the year, counted at the age
            they are on the following 1 January, already net of their own
            mortality during the year.

    Returns:
        (population on 1 Jan next year, births during the year).
    """
    L = pop.shape[0]

    aged = np.zeros_like(pop)
    aged[:, :, 1:MAX_AGE] = pop[:, :, 0 : MAX_AGE - 1] * sx[:, :, 1:MAX_AGE]
    # Both the 99-year-olds and the existing 100+ group end up in 100+, and the
    # UN's Sx for the open group is defined to apply to their sum.
    aged[:, :, MAX_AGE] = (pop[:, :, MAX_AGE - 1] + pop[:, :, MAX_AGE]) * sx[:, :, MAX_AGE]

    if migration is not None:
        aged += migration

    # Mid-year women, by age, for the fertility rates to act on.
    exposure = 0.5 * (pop[:, FEMALE, :] + aged[:, FEMALE, :])
    births = np.einsum("la,la->l", exposure, asfr)

    female_share = 1.0 / (1.0 + srb)
    aged[:, FEMALE, 0] += births * female_share * sx[:, FEMALE, 0]
    aged[:, MALE, 0] += births * (1.0 - female_share) * sx[:, MALE, 0]

    # A population is a count of people and cannot go negative. Migration
    # assumptions occasionally try, in small territories with large outflows.
    np.maximum(aged, 0.0, out=aged)
    return aged, births


def project(
    pop0: np.ndarray,
    *,
    start_year: int,
    sx: np.ndarray,
    asfr: np.ndarray,
    srb: np.ndarray,
    migration: np.ndarray | None = None,
    locations: list[str] | None = None,
    n_years: int | None = None,
) -> ProjectionResult:
    """Run the projection forward.

    Rate arrays are indexed by projection step: axis 0 entry 0 is calendar year
    `start_year`. If a rate array is shorter than `n_years` its final year is
    held constant for the remainder. That is what makes runs past 2100 possible
    at all — nobody publishes rates out there — and it is a real assumption, so
    scenarios that rely on it should say so.

    Raises on anything that would silently produce nonsense: wrong shapes,
    negative counts, fertility outside childbearing ages.
    """
    pop0 = np.asarray(pop0, dtype=np.float64)
    if pop0.ndim != 3 or pop0.shape[1:] != (N_SEXES, N_AGES):
        raise ValueError(f"pop0 must be (L, 2, {N_AGES}); got {pop0.shape}")
    if np.any(pop0 < 0):
        raise ValueError("pop0 contains negative population")

    L = pop0.shape[0]
    if n_years is None:
        n_years = min(a.shape[0] for a in (sx, asfr, srb))
    if locations is None:
        locations = [str(i) for i in range(L)]
    if len(locations) != L:
        raise ValueError(f"{len(locations)} location labels for {L} locations")

    _check_rate(sx, "sx", L, (N_SEXES, N_AGES))
    _check_rate(asfr, "asfr", L, (N_AGES,))
    _check_rate(srb, "srb", L, ())
    if migration is not None:
        _check_rate(migration, "migration", L, (N_SEXES, N_AGES), allow_negative=True)

    outside = float(
        np.abs(asfr[..., :FERT_AGE_MIN]).sum() + np.abs(asfr[..., FERT_AGE_MAX + 1 :]).sum()
    )
    if outside > 0:
        raise ValueError(
            f"asfr is non-zero outside ages {FERT_AGE_MIN}-{FERT_AGE_MAX} "
            f"(total {outside:g}); that is almost certainly an age-indexing bug"
        )

    population = np.empty((n_years + 1, L, N_SEXES, N_AGES))
    births = np.empty((n_years, L))
    deaths = np.empty((n_years, L))
    population[0] = pop0

    for t in range(n_years):
        mig_t = _year(migration, t) if migration is not None else None
        nxt, b = step(population[t], _year(sx, t), _year(asfr, t), _year(srb, t), mig_t)
        population[t + 1] = nxt
        births[t] = b
        inflow = b + (mig_t.sum(axis=(1, 2)) if mig_t is not None else 0.0)
        deaths[t] = population[t].sum(axis=(1, 2)) + inflow - nxt.sum(axis=(1, 2))

    return ProjectionResult(
        years=np.arange(start_year, start_year + n_years + 1),
        population=population,
        births=births,
        deaths=deaths,
        locations=list(locations),
    )


def tfr(asfr: np.ndarray) -> np.ndarray:
    """Total fertility rate: the sum of single-age rates. Shape (..., 101) -> (...)."""
    return asfr.sum(axis=-1)


def _year(arr: np.ndarray, t: int) -> np.ndarray:
    """Rates for step t, holding the last available year constant past the end."""
    return arr[min(t, arr.shape[0] - 1)]


def _check_rate(
    arr: np.ndarray, name: str, n_loc: int, tail: tuple[int, ...], *, allow_negative: bool = False
) -> None:
    expected = (n_loc,) + tail
    if arr.ndim != 1 + len(expected) or arr.shape[1:] != expected:
        raise ValueError(f"{name} must be (T, {', '.join(map(str, expected))}); got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        bad = int(np.count_nonzero(~np.isfinite(arr)))
        raise ValueError(f"{name} has {bad} non-finite value(s)")
    if not allow_negative and np.any(arr < 0):
        raise ValueError(f"{name} has negative values")

# After the UN boundary

> **Fertility and mortality are no longer frozen after 2100.** They are continued
> by the same kind of emulator this document describes for migration; see
> [Fertility and longevity after 2100](#fertility-and-longevity-after-2100) at
> the end. The `--post-2100 hold` flag on `run_uw_ensemble.py` reproduces the old
> frozen-rate behaviour, which is kept so the cost of that assumption can be
> measured rather than argued about.

## Stochastic migration

## The project boundary

The model now distinguishes three scientific objects:

1. **UN reproduction:** WPP 2024 through 2100. No project-generated value is
   labelled as an official UN projection after that boundary.
2. **UN project extension:** starts from the WPP population on 1 January 2100
   and runs to 2150. Fertility, mortality and the sex ratio are held at their
   final WPP age schedules. Migration is continued stochastically.
3. **Selection model:** a separate model that forks in 2024, so selection acts
   over the entire projection rather than being switched on after the UN path
   has already determined the 2100 population.

The extension is a reference calculation, not the project's primary scientific
claim. The selection model remains the main focus.

## What is actually available

The University of Washington archive contains 1,000 annual `bayesMig` net
migration-rate trajectories for 236 locations from 2023 through 2100. Its
README records that the paths came from the hierarchical AR(1) model of Azose
and Raftery, using three 50,000-iteration MCMC chains. It does **not** include
the fitted MCMC state. Therefore the project cannot simply ask the original fit
to continue for another fifty years.

The source archive is pinned in `data/manifest/uw_wpp2024_migration.json`. The
large archive and extracted CSV remain ignored; the checksum, reader, method,
tests and compact result summary are committed.

## The continuation

For each country, the project fits the published model's AR(1) form to the late
portion of all 1,000 paths, 2070-2100:

```text
rate[t] = mu + phi * (rate[t-1] - mu) + Normal(0, sigma)
```

Every continuation begins at that trajectory's own published 2100 rate. A
pinned random seed generates annual innovations through 2149. This retains the
source distribution at the boundary and makes the post-2100 calculation
reproducible.

This is explicitly a **model-output emulator**. It uses the same mathematical
form as `bayesMig`, but the fitted parameters are reconstructed from its output
rather than taken from the missing posterior state. It must not be described as
an official UN or UW projection to 2150.

## Global balancing

The public UW archive is close to zero when averaged over trajectories, but its
individual trajectories are not globally balanced. At 2100, individual paths
implied world discrepancies as large as roughly 23 million net migrants in one
year when the rates were converted to counts using the reference population.

Using those paths directly caused the previous uncertainty decomposition to
mistake the creation or deletion of people for migration uncertainty. The old
claim that migration contributed a 1.75-billion world range at 2150 was
therefore wrong.

The extension corrects this every draw and year:

1. Apply each country's rate to that draw's current population.
2. Compute the worldwide count discrepancy.
3. Shift active-country rates by a common amount, which redistributes the
   discrepancy in proportion to current populations.
4. Assert that worldwide net migration is zero to numerical precision.

The UN uses a more detailed staged balancing procedure, including special
treatment of labour-migration countries. The project method implements the
essential accounting constraint and is labelled as an approximation.

## Age and sex

The total rate source has no single-year age and sex detail. The project borrows
a country-specific schedule from the absolute values of the UN medium-path
migration residual. This shape is a scenario assumption, not independent
evidence.

For immigration, the schedule is applied directly. For emigration, a schedule
can occasionally request more people from a narrow age/sex cell than exist.
Instead of allowing the cohort engine to clip the cell to zero—and thereby
silently create people—the unmet removal is redistributed across populated
cells while preserving the country's requested net count.

## Current result

With 1,000 paths, fixed post-2100 fertility and mortality, and migration as the
only varying component:

| Population date | Median world population | 90% range |
| --- | ---: | ---: |
| 2100 | 10.187 billion | fixed boundary state |
| 2125 | 9.573 billion | 9.555-9.588 billion |
| 2150 | 8.725 billion | 8.656-8.772 billion |

When migration uncertainty is isolated over the **whole 2024-2150 period**, its
globally balanced contribution to the 2150 world 90% width is **0.34 billion**,
not 1.75 billion. The indirect world effect remains nonzero because relocating
people changes the fertility and mortality schedules they experience.

At the country level the range remains large. At 2100, migration uncertainty is
about 42 times the fertility uncertainty for the United Arab Emirates, four
times for Canada, and about one-sixteenth as large for Nigeria.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\run_un_extension.py
.\.venv\Scripts\python.exe scripts\plot_un_extension.py
.\.venv\Scripts\python.exe scripts\decompose_uncertainty.py --draws 200 --migration-only
.\.venv\Scripts\python.exe scripts\plot_decomposition.py
```

The durable numerical receipt is
`data/reference/un_project_extension_summary.json`; the review figure is
`docs/un-project-extension.svg`.

## Fertility and longevity after 2100

Added 2026-08-16. `src/popmodel/rates.py` continues the published fertility and
life-expectancy trajectories in the same spirit, and for the same reason: the
alternative was holding them constant, which is a strong claim about half the
distance to 2150 dressed up as housekeeping.

The two components need different treatments, and getting that wrong is the
whole risk:

* **Fertility is stationary inside a trajectory.** Fitted over 2070-2100, each
  path fluctuates around its own level with an autocorrelation near 0.89 and a
  stationary spread near 0.12 children, while the spread *between* trajectories
  at 2100 is about 0.40. Each path is therefore continued as an AR(1) around
  **its own 2100 value**. Fitting the AR(1) across trajectories instead would
  estimate one level per country, return an autocorrelation near one, and drag
  every draw toward that level — deleting the posterior spread while producing
  entirely plausible-looking output. `tests/test_rates.py::test_between_draw_spread_survives`
  exists to catch exactly that.
* **Longevity is still trending.** The annual gain in female life expectancy
  averages 0.114 years over 2070-2100 and is uniform across countries
  (0.100-0.154). Each path continues as a random walk with its country's fitted
  drift plus AR(1) noise on the gain. The male series is derived from the female
  series and a separately continued sex gap, so the two cannot cross.

Two biases are stated rather than buried, and both point the same way. Centring
each fertility path on its 2100 value drops the small residual downward drift
still present at the boundary, which would otherwise subtract about 0.15 children
by 2150. And the continuation does not reproduce bayesLife's deceleration, in
which gains slow as life expectancy rises. Both make the result slightly higher
than a more faithful continuation would.

The age **patterns** are still held at their final published shape — the shape of
fertility across ages, and the mortality standard the Brass logit is applied to.
That is a much weaker assumption than holding a level, and it is carried by
`ReferenceSchedules.hold_final_pattern`, which is off by default so that a
silently repeated schedule cannot happen by accident.

### The rails, and why they are derived rather than written down

Continued values are clipped only if they leave the range the source archive
itself occupied, padded by a quarter of its width, by four innovation standard
deviations, and — for a trending series — by as far as its own fitted trend can
carry it. All three corrections came from a check that fired when it should not
have:

* A first version bounded the female-male life-expectancy gap at 0 and 15 years
  and clipped a tenth of all values, because the source's own gap runs from
  -6.6 to +20.2.
* A width-proportional pad on fertility put the floor at -1.45, because
  fertility spans 0.33 to 7.27 across the archive, so the rail permitted a
  negative birth rate.
* A rail from the observed range binds immediately on a trending series, because
  leaving that range is what a trend does.

On the real archive the rails now clip about three values in every million.
A rail that fires on ordinary source behaviour is not a safety check; it is a
silent model.

### Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\run_uw_ensemble.py --output out\uw_ensemble_continued.json
.\.venv\Scripts\python.exe scripts\run_uw_ensemble.py --post-2100 hold --output out\uw_ensemble.json
```

Both propagate the same posterior through the same engine and differ only after
2100, so the difference between them is exactly the cost of the frozen-rate
assumption. That replaces the older proxy, which truncated the source data ten
years early to estimate the same thing.

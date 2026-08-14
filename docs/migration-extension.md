# Stochastic migration after the UN boundary

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

# Handoff — picking this project up cold

Written for whoever works on this next, human or model. `CLAUDE.md` is the
short list of rules. This is the longer briefing: what exists, what is verified,
what will bite you, and what to do next.

> **Start with `NEXT_SESSION.md`.** It contains Dylan's clarified end goal,
> current session status, the exact next task, and a link to `LOCAL_TOOLS.md`,
> where the actual R, Rtools, Python, Tectonic, archive, and export paths are
> recorded. This file is the deeper technical history.

---

## 1. What this is

An interactive world map backed by a demographic projection that runs to 2150,
which keeps a scored record of its own predictions. Click a country, see its
population pyramid and its path to 2150.

The point is **not** forecast accuracy. The UN will beat this model at 2050 and
that is fine and expected. The point is a model that can be wrong *for a stated
reason*, and a track record that can be graded decades later. Read
`spec/population-2150-spec-v0.3.md` §3 before §5 — several architectural
choices look wrong if you assume accuracy is the goal.

The one substantive claim underneath everything: by 2150 essentially nobody
alive today is still alive, so the answer is dominated entirely by the long-run
fertility process. A long-run fertility of 1.85 versus 1.30 is a 4.4×
difference in world population at 2150, from a parameter nobody can measure.
Precision in the base data is nearly irrelevant; precision about the mechanism
is everything.

## 2. Read in this order

1. `spec/population-2150-spec-v0.3.md` §3 (philosophy), then §5 (architecture).
2. `CLAUDE.md` — the standing rules. They are not stylistic.
3. This file, §7 and §8 especially.
4. The header comment of `src/popmodel/engine/cohort.py` before touching the engine.

### Whose words these are

The spec takes strong positions, and most of them were argued by an assistant
and accepted by Dylan rather than stated by him. That distinction is easy to
lose and worth keeping, because a model that reads them as his convictions will
defend them on his behalf, and he would rather they were argued with.

Named examples, all of them assistant reasoning that he agreed to, not his
stated preferences:

- **Section 3.1, "Gelman, not Jaynes."** Dylan likes Jaynes. The judgement that
  Jaynes's approach was the wrong fit for this project is the assistant's; he
  decided to trust it. If the evidence points the other way, say so.
- **Section 3.3, that the UN's programme is degenerating in Lakatos's sense.**
- **Section 3.5, that accuracy is not the criterion.**
- **Section 6.1, that simple ecological population biology is a dead end here.**

This is not an invitation to relitigate everything. It is a warning about a
specific failure this project has already suffered once: spec section 8's
244-billion test came from an offhand remark in the chat that produced the spec,
hardened into a stated requirement, and was wrong (see section 8 below). The
same mechanism turns an opinion into an instruction.

**The standing rules in `CLAUDE.md` are different and do bind.** The discipline
around checking figures, tracing values to sources and marking preliminary data
lives there deliberately: Dylan removed those lines from his own global
instructions in August 2026 because they were never his words, and confirmed he
wants them kept for this project because they have earned their place. They
caught the empty pyramids, the country export labelled with the wrong ISO code,
and the migration reshape that gave one country another country's migrants.

## 3. What is built, and what verifies it

Phases 1, 2 and 3 of the spec's six are done. Every number below is regenerated
by a script; none is typed by hand.

### Phase 2 — the projection engine (`src/popmodel/engine/cohort.py`)

Cohort-component projection, single year of age 0–100+, by sex, 237 countries.
Contains **no theory about the future**: it takes fertility, mortality and
migration as given and does the bookkeeping. That is deliberate, so later
results can be attributed to a mechanism rather than to arithmetic.

Verified by `scripts/validate_engine.py`, which must pass before anything else
is trusted:

| Check at 2100 | Result | Limit |
|---|---|---|
| World population, UN zero-migration variant | **0.001%** | 0.05% |
| Any country over 10,000 people | worst **0.13%** | 0.5% |
| Any five-year age group under 100 | worst **0.006%** | 0.05% |
| Open 100+ group | 1.08% | 2% |
| Constant fertility at 2100 vs the UN's own | **0.05%** | 0.5% |

The zero-migration variant is the real test: every input is published, nothing
is tuned, and any discrepancy is our arithmetic being wrong. The medium variant
is reported as a **diagnostic, not a test**, because its migration term is a
residual backed out of the UN's own medium path — see §8.

The older deterministic diagnostic peaks at **10.29 billion in 2084** and falls
to **8.78 billion by 2150**. Only its path through 2100 is the UN reproduction;
after 2100 it freezes final rates and migration counts and is now a legacy
comparison. Constant fertility gives **53 billion**, which is the absurdity
check.

### Phase 1 — the backtest (`src/popmodel/backtest.py`)

Grades eight archived UN revisions (1992–2008) against WPP 2024's estimates.
Run with `scripts/run_backtest.py`.

- World population under-projected by **2.45%** on average, and in the same
  direction in every revision since 1996. A consistent sign is a bias, not
  noise — that distinction is the whole finding.
- African fertility **9.8% too low**; East Asian fertility **14.9% too high**;
  life expectancy **1.32 years too low**. The spec predicted all three.
- **41 of 117** world-level projections landed inside the revision's own
  low-to-high band.

Two honesty constraints are enforced in the code, not just mentioned: the
comparison is against WPP 2024's *estimates*, which are a model output rather
than ground truth (spec rule 3); and the low/high variants are fertility
scenarios with no probability attached, so coverage is reported as "was reality
inside the printed range", never as calibration.

Graded at world and continental-region level, not by country: UN region codes
mean the same thing in 1992 and now, whereas the USSR, Yugoslavia,
Czechoslovakia, Sudan and Ethiopia all changed shape inside the window.

### Phase 3 — map, pyramids, crosswalk, confidence layer

- `index.html` at the repo root: one self-contained page, no external requests,
  no build step, no framework. Equal Earth projection (equal-area — Mercator
  would inflate Greenland to look larger than Africa on a *population* map).
- `src/popmodel/crosswalk.py` — all 237 countries matched to map shapes.
- `src/popmodel/export.py` — per-country pyramids, 1950–2150.
- `src/popmodel/ingest/census.py` — the data-confidence layer.

### Infrastructure that outlives the model

- `src/popmodel/track/` — immutable prediction vintages and proper scoring
  rules (CRPS checked against its closed form). Spec §9 calls this the actual
  contribution; the model is replaceable.
- `src/popmodel/sources/fetch.py` — every download checksummed, manifests
  committed. A file the UN silently reissues fails loudly.

### Phase 4 — the probabilistic baseline (complete)

UW's Bayesian posterior for fertility and mortality, plus their separate
migration model, propagated through the engine one draw at a time. 1,000 draws,
236 countries, 2024 to 2150.

**What it says.** World population median peaks at **10.31 billion in 2093** and
reaches **9.73 billion by 2150**, with a 90% band of **6.97 to 14.36 billion**.
57% of draws peak before 2100. Nigeria's 2150 band runs from 80 million to 1.34
billion, which is the project's argument in one chart.

**What makes it believable.** Two checks nobody arranged: the deterministic run
on the UN's own assumptions peaks at 10.29 billion in 2084 against the
ensemble's 10.31 billion in 2093; and the deterministic 2100 figure lands inside
the ensemble's 5-95% band for **97% of countries**. Those two runs share only the
engine.

**What it is not.** UW's model is mean-reverting, so this band expresses the
conventional long-run assumption — the one standing instruction 8 declines to
adopt by default. It is the **conventional mean-reverting comparator**, not the
UN reproduction. The stored vintage marks every quantity `is_project_claim: false`, and
recording it before Phase 5 exists is what stops the comparison being arranged
afterwards.

The pieces, in the order they run:

- `sources/uw_wpp2024.py`, `scripts/fetch_uw_posteriors.py`,
  `sources/uw_extract.py` — the two annual archives pinned, fingerprinted and
  safely unpacked. UW publishes no checksum, so the recorded one is ours.
- `r/uw-extract/extract_all_countries.R`, `scripts/export_uw_all.py` — all 236
  locations through UW's own public accessors, loading the objects once instead
  of per country. The bulk script is a second implementation of the validated
  single-country one, so the driver re-exports Finland and Nigeria through it
  and compares byte for byte.
- `ingest/uw_bundle.py` — the 236 exports compacted into one array file, and the
  statement of what makes a world total meaningful: trajectory *k* in every
  country is one posterior sample.
- `bayes/schedules.py` — **the modelling decision.** UW gives one fertility
  number and two mortality numbers per country-year; the engine needs a hundred.
  The UN's own age patterns are borrowed and only their level is moved:
  fertility rescaled to the drawn total, mortality shifted by a single Brass
  logit solved to the drawn life expectancy. Both reproduce their input to
  machine precision. `scripts/check_schedules.py` proves it on the real
  1,000-trajectory exports; `docs/schedules.svg` shows the schedules it invents.
- `ingest/uw_mig.py`, `scripts/build_uw_migration.py` — bayesMig, plain CSV, no
  R needed. Three stated decisions turn a national rate into migrants by age and
  sex; see the module docstring, and §8 below for the trap in it.
- `scripts/run_uw_ensemble.py` — predictive checks, then the run. Writes a
  receipt naming every assumption.
- `scripts/write_uw_vintage.py`, `scripts/plot_ensemble.py` — the write-once
  record and the figure.

### UN project extension — the explicit 2100 boundary

The official reproduction now stops at 2100. `scripts/run_un_extension.py`
starts from the published WPP population on 1 January 2100, holds the final
fertility and mortality age schedules, and continues migration through 1,000
stochastic paths to 2150.

UW's public migration archive contains trajectories but not the fitted MCMC
state. `src/popmodel/migration.py` therefore fits the published AR(1) form to
the 2070-2100 portion of those paths and is labelled a model-output emulator,
not an official continuation. Every rate is applied to that path's evolving
population and every draw-year is population-weight balanced to exactly zero
world net migration. Impossible age-cell emigration is redistributed rather
than silently clipped.

The median world result is 8.725 billion in 2150, with a migration-only 90%
range of 8.656-8.772 billion. See `docs/migration-extension.md`, the committed
receipt `data/reference/un_project_extension_summary.json`, and
`docs/un-project-extension.svg`.

### Phase 5 — the mechanistic layer (complete)

The thing the project is actually about. Selection and transmission on one side,
a changing fertility environment on the other, and observed fertility as the
output of both rather than an input to either.

`src/popmodel/mech/` keeps spec section 5.3's two questions apart:
`composition.py` decides who becomes more common, `environment.py` decides what
a given disposition produces, `engine.py` is the cohort engine with a
composition axis and no opinions, `runs.py` maps spec section 8's declared
scenarios onto those settings.

**What makes it trustworthy.** With every propensity set to one, the typed
engine reproduces the ordinary engine to 3e-16 relative, and the legacy
deterministic cell of the grid lands at 8.78 billion in 2150 - that diagnostic's
figure. Any difference between Phase 4 and Phase 5 is therefore the mechanism
and not a second implementation of the arithmetic. One generation of selection
also matches the observed parent-offspring covariance response to nine decimal
places, which is the mechanism agreeing with its calibration.

**What it says, reframed selection-first on 2026-08-14.** The cleaner benchmark
is the stable-low path with no extra post-2050 environmental decline, followed
by measured mainstream selection. That raises the 2150 world result from 8.54
to 10.36 billion. Named groups and one defector-routing knob add only another
0.05 billion. The old 4% development-pressure scenario then removes 2.79
billion and lands at 7.61 billion, so the unsourced environmental knob was
controlling the headline.

The primary result is now the break-even boundary rather than the 7.61-billion
stress test. At the central measured family-size spread and parent-child
persistence, an additional uniform environmental decline of **1.53% per
decade** after 2050 cancels mainstream selection by 2150. The reproducible
analysis is `scripts/analyze_selection_break_even.py`, its committed numbers are
`data/reference/selection_break_even_sensitivity.json`, and the figure is
`docs/selection-break-even.svg`. The 4% path remains available, explicitly as an
illustrative stress test rather than a forecast of the economy.

**What it rests on.** `data/reference/mechanism_parameters.csv`, thirteen
parameters. All eight sourced rows were checked against their evidence on
2026-08-13; `docs/mechanism-parameter-audit.md` records every decision and link.
The last gap, `mainstream_propensity_cv`, is now calculated from 43 pinned CFE
country files and independently checked against CDC U.S. cohorts. Five rows are
scenario knobs with no independent support. The loader refuses a row with no provenance,
a "sourced" row with no evidence, and a knob that claims to be verified. Every
output repeats the caveat. **The architecture is sound and the magnitudes remain
conditional** on explicit future paths, empirical ranges, and structural choices.

### The uncertainty decomposition

`scripts/decompose_uncertainty.py` varies one source at a time across its own
draws and holds the rest at a median trajectory. World 90% width at 2150, in
billions: **fertility 7.26, the mechanism 5.72, migration 0.34, our own
hold-constant rule after 2100 0.73, mortality 0.52.**

The country panel matters more than the world one because it disagrees with it.
At 2100, migration is **42.2 times** fertility for the United Arab Emirates and
**0.06 times** it for Nigeria. Which uncertainty dominates is a fact about where
you look, and the band published on the map contains no migration uncertainty at
all - one shared median path per run.

The previous 1.75-billion migration width was wrong: the public UW migration
paths are balanced in expectation, not draw by draw, so the old calculation
allowed some trajectories to create or delete millions of people globally.
The corrected decomposition applies rates to evolving populations and enforces
zero world net migration in every draw-year.

This is the page's organising idea now, on Dylan's direction: what earns trust
is showing the kinds of uncertainty represented correctly, not grading somebody
else's forecasts. See `NEXT_SESSION.md`.

## 4. What is not built

- **Phase 6, scoring runs.** Formats are fixed, two vintages are stored, and
  nothing resolves before about 2038. WPP 2027 is the next data event.
- **Migration uncertainty in the interactive Phase 4 band.** Correctly measured
  at 0.34 billion of world width and most of the answer for the Gulf states,
  but still excluded there because that older ensemble takes one shared median
  path per run. The separate UN project extension does include it after 2100.
- **Per-country uncertainty decomposition.** Computed for the world and six
  watch countries; widening it to all 236 is small work.
- **Survey coverage and vital-registration completeness** in the confidence
  layer. Only census recency is sourced. Do not invent the other two.
- **The three finished outputs**, none of them started beyond scaffolding, and
  all of them waiting on the science being worth publishing:
  a genuinely public webpage (the live page is still the authenticated hub);
  the paper (`paper/` is an early scaffold, not an approved draft); and a
  YouTube bar-chart race (`scripts/render_race.py` renders frames, and that is
  all that exists). `NEXT_SESSION.md` carries the notes on each.

## 5. Rules that must not break

The eight standing instructions are in `CLAUDE.md` and come from spec §14. The
two that get broken by accident:

- **Never fit a mechanism parameter to the series it is meant to explain.** If
  it cannot be sourced independently it is a scenario knob and must be labelled
  one. There is a `scenario_knobs` field for exactly this.
- **Fail loudly on unmatched country codes.** Every join in this repo raises
  rather than drops. A map missing nine countries looks exactly like a map that
  has them.

And one structural rule: `ingest/wpp.py` produces engine **inputs**;
`ingest/reference.py` produces **targets** the engine is scored against.
Nothing in the engine or a scenario may import `reference.py`.

## 6. Running the whole thing

Python 3.11+. `numpy` and `pandas` for the core; `xlrd` for the backtest,
`matplotlib` for figures. Nothing else.

```bash
python scripts/fetch_wpp.py          # ~1.2 GB of UN data, once
python scripts/build_bundle.py       # CSV -> arrays, ~90s
python scripts/validate_engine.py    # THE engine test; must pass first
python scripts/run_to_2150.py        # scenarios to 2150
python -m pytest tests/ -q           # fast tests, no data needed
```

Phase 4, the probabilistic baseline. The archives are already downloaded and
their checksums committed; `--check` verifies them without re-fetching.

```powershell
$rscript = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe'
python scripts\fetch_uw_posteriors.py --check
python scripts\unpack_uw_posteriors.py
python scripts\export_uw_all.py --rscript $rscript   # 236 countries, ~25 min
python scripts\build_uw_bundle.py                    # 421 MB array bundle
python scripts\build_uw_migration.py                 # bayesMig, no R needed
python scripts\check_schedules.py                    # the converter checkpoint
python scripts\run_uw_ensemble.py --draws 25         # predictive check first
python scripts\run_uw_ensemble.py                    # all 1,000, ~30 min
python scripts\write_uw_vintage.py
python scripts\plot_ensemble.py
```

All local runtime paths are recorded in `LOCAL_TOOLS.md`.

Phase 5, the mechanism, and the decomposition. Neither needs R.

```bash
python scripts/run_phase5.py                    # the two-axis grid
python scripts/run_phase5.py --ensemble 200     # with parameter uncertainty
python scripts/plot_phase5.py
python scripts/analyze_selection_break_even.py  # selection-first boundary + ladder
python scripts/plot_selection_break_even.py
python scripts/decompose_uncertainty.py --draws 200   # about 25 minutes
python scripts/plot_decomposition.py
```

Backtest (needs the archives, ~590 MB):

```bash
python scripts/fetch_archive.py
python scripts/run_backtest.py
python scripts/plot_backtest.py
```

Map and confidence layer (needs the geometry, ~6 MB):

```bash
python scripts/fetch_geometry.py
python scripts/build_crosswalk.py
python scripts/build_census.py
python scripts/build_site_data.py
python scripts/plot_model_flow.py     # conceptual UN/model comparison
python scripts/build_map.py
python scripts/check_map.py          # verifies the page without a browser
```

Paper and reviewed public payload:

```bash
python scripts/build_paper.py
python scripts/build_public.py
```

## 7. Conventions you will get wrong if you guess

- **Ages** 0–100, where 100 means 100+. **Sex** 0 = female, 1 = male.
- **`sx[a]` is survival INTO age a**, not out of it. This is the UN's own `Sx`
  convention, adopted deliberately so the numbers in the engine are the numbers
  in the source file with no translation step. `sx[0]` is birth survival
  (`L0/l0`, not `p(0)` — a baby born in July is exposed for half a year).
  `sx[100]` applies to the **sum** of the 99-year-olds and the existing 100+
  group.
- **Populations are people, not thousands.** WPP publishes thousands; the ×1000
  happens exactly once, in `ingest/wpp.py`.
- **Fertility rates are births per woman per year.** WPP publishes per 1000.
- **Childbearing ages are 10–54, not 15–49.** See §8.
- **Populations are dated 1 January.** Rates supplied for step *t* are the ones
  in force during calendar year *t*.
- **Age-specific fertility uses MID-year women**, so the denominator is the
  average of the 1 January figure and the following 1 January figure. Getting
  this wrong biases births by roughly half a year of cohort change — small in
  one year, not small after 126.

## 8. Traps that produce plausible wrong answers

Each of these was found by a wrong number, not by reading. None of them errors.

**Mothers under 15 and over 49.** WPP's single-age fertility file covers 15–49;
its five-year file covers 10–54. The missing mothers are ~0.3% of world births.
Left out, the projection ran 0.3% low at 2100 with the error still growing. The
ingest now assembles both files and refuses to build unless the result
reproduces the UN's published total fertility rate.

**The spec's 244-billion test does not work.** Spec §8 says constant fertility
should reach ~244 billion by 2150 or the engine has a bug. That figure came
from the UN's 2004 long-range report, built on the *2002* revision. Constant
fertility freezes the base year's rates, and those have fallen a great deal
since 2002 — hitting 244 billion from a 2024 base would mean the engine was
*wrong*. Replaced by a comparison against the UN's own WPP 2024
constant-fertility variant. (That figure originated as an offhand remark in the
chat that produced the spec, and hardened into a requirement. Be careful which
numbers you write down as authoritative.)

**The UN's constant-fertility variant freezes 2023, not 2024.** About 0.6%
higher than the 2024 medium rates, which compounds to 2.7% by 2100. The
scenario reads the UN's own frozen rates rather than assuming ours.

**Migration is a residual, not an estimate.** The UN does not publish net
migrants by single year of age, so `derive_migration` backs them out of the UN's
own medium path. That is a usable forward-model input and is **not evidence of
anything** — it absorbs every difference between their procedure and ours. Any
run using it is labelled a diagnostic.

**Archived WPP revisions are Excel workbooks, not scans.** All fourteen back to
1992, from the downloads page under file type "Archive", using the same country
codes still in use. A previous session recorded the opposite and skipped phase 1
for it.

**The archives ship counterfactual scenarios beside the real projection** — "no
AIDS", "instant replacement", "zero migration", "constant mortality". They are
excluded by name in `sources/wpp_archive.py`. Grading a counterfactual as a
forecast would be a serious error, not a rounding problem.

**Archive layout drifts between revisions.** `ingest/archive.py` locates the
header row rather than assuming a row number, and the life-expectancy workbooks
changed shape entirely between 2004 and 2006.

**A country code and an ISO3 code that disagree do not error anywhere.**
`export_uw_fixture.py` took both as separate arguments and defaulted the ISO3 to
Finland's, so exporting Nigeria stamped it FIN and the schedule converter
projected Nigeria on Finland's fertility and mortality. Every checksum passed.
The only symptom was a mortality adjustment ten times larger than it should have
been, which is why `ScheduleDiagnostics` reports the size of that adjustment.
The ISO3 code now comes from the committed crosswalk and the export validator
rejects a mismatched pair.

**The bayesMig export is ordered by that model's own region order, not by
country code.** Reshaping it without reordering hands one country another
country's migration and produces a world total that looks like a result - the
first run showed migration as a wider world band than fertility, which is
impossible because migration cancels globally. The reader now checks that the
median of the reshaped draws reproduces the median grid built independently by a
groupby, which catches it in one line.

**A regular expression that loses its backreference deletes what it matched.**
The figure inliner's substitution ate the opening svg tag and produced a page
with no figure and no error. Anything that strips attributes from markup now
splits the tag rather than substituting into it.

**A test harness that shares one stub element across ids will lie to you.**
`check_hover.js` returned the same fake element for every `getElementById`, so
the readout text overwrote the captured SVG and the check reported "no path
drawn" for a page that draws one perfectly well.

**Never sum country quantiles to get a world quantile.** Adding up every
country's 5th percentile assumes all 236 land in their own bad tail in the same
draw. The world's 2150 5th percentile is 6.97 billion; summing the countries'
would say 3.13 billion. The page is passed a world band computed from each
draw's own world total, and `check_map.py` prints both numbers so the shortcut
stays visibly wrong.

**The bayesMig archive does not say what its rate is a rate of.** It is net
migrants per person per year, checked rather than assumed: rate times 1 January
population reproduces WPP's own published net migration to 0.2% for the United
States and 0.3% for India. `build_uw_migration.py` asserts this before writing
anything. The age and sex composition is separately borrowed from the UN's
residual and is not independent evidence.

**The census page has three separate traps** (`ingest/census.py`):
a country that ran two censuses in one round gets a **continuation row with a
blank name**, and the UK's own row is empty because its censuses sit under
England and Wales, Scotland and Northern Ireland — dropping those put the UK at
"no census since 1985" and moved 32 countries when fixed; **section headings
live inside the first country's own cells**, which silently deleted Afghanistan
and the first country of every continent; and **parenthesised dates are censuses
that have not happened yet**.

**Rounding pyramids to thousands empties small countries.** Tuvalu has 11,000
people across 101 ages and two sexes, so every cell rounds to zero. Seven
countries had entirely empty pyramids and Iceland lost 3%. Stored in people now,
and `check_map.py` asserts every pyramid sums to its country's total.

**Join on codes, never on names, unless there is no code.** Natural Earth
carries the UN's own M49 numeric code, which is what WPP uses as its LocID —
that matches 228 of 237 outright. The census page has no codes, so it is matched
by name with normalisation plus an explicit override table, and it raises on
anything left over. It raised four times before all 237 were accounted for, and
one of those failures was an override that mapped a correct exact match onto a
WPP spelling that did not exist.

**Natural Earth is pinned to release `v5.1.2`, not `master`.** A shape that
moves under a stored prediction is the same problem as a data file that moves.

## 9. How verification works here

The browser tooling is currently off, so nothing is checked by looking at a live
page. The pattern that replaced it, and which is better discipline anyway:

- **Figures**: write a PNG next to the SVG and actually open the PNG. A
  simplification tolerance that flatters Russia deletes Malta, and no error is
  raised either way.
- **The map**: `check_map.py` parses the embedded data back out and checks it is
  complete and self-consistent, runs the inline JavaScript through
  `node --check`, and **redraws both choropleths in Python from the page's own
  numbers** so the colour scale and the arithmetic can be looked at. That last
  check is what caught the empty-pyramid bug.
- **Every layer raises rather than degrades.** Prefer a build that stops to one
  that produces a plausible file.

## 10. Where the numbers live

- `out/*.json` — validation, scenario runs, backtest. Regenerable, gitignored.
- `data/reference/*.csv` — crosswalk and census tables. **Committed**, so the
  decisions about Kosovo, Gibraltar and the French overseas departments are
  reviewable as text rather than buried in code.
- `data/manifest/*.json` — SHA-256 of every downloaded file. **Committed.**
- `vintages/` — stored predictions, written once, never overwritten.
  `track.vintage.write` raises rather than overwrite; do not add a `force` flag.

## 11. Deploying

The map is served at `hub.dylanslagh.com/population-model/`, password-gated,
and now carries the Phase 4 uncertainty band on every country. The repository
also contains an early LaTeX/PDF paper scaffold, a paper landing page, and
`scripts/build_public.py`, which stages the reviewed map and paper surface into
`dist/`. The scaffold is not an approved paper; see `NEXT_SESSION.md`. No
genuinely public host is configured yet.

The hub is a separate repo (`project-hub`) that clones every project and
publishes them as one site. Two things that matter here:

- The page must be `index.html` **at the repo root** and **committed**. The hub
  publishes only what git tracks; a page generated into a gitignored folder
  shows up as a file listing with no error anywhere.
- **Pushing this repo does not rebuild the hub.** Fire `project-hub`'s "Publish
  the hub" workflow afterwards (`gh workflow run publish.yml --repo
  dylanslagh/project-hub`), or it waits up to six hours for the scheduled run
  and Dylan reviews a stale page.

## 12. What to do next

**The completed-family-size dispersion job is finished.** The reproducible CFE
calculation, CDC cross-check, interpretation, and projection sensitivity are in
`docs/mechanism-parameter-audit.md`; source checksums and derived outputs are
committed. The central CV changed 0.60 -> 0.57 and the race result 7.75 -> 7.61
billion. All eight sourced mechanism rows are now verified. Do not reopen this
by fitting a latent-trait variance to the projection it is meant to explain.

**Top priority: connect the stochastic migration paths to the paired selection
comparison.** Keep the selection fork at 2024 and give each reference/selection
pair the same source draw and post-2100 innovations, so the difference isolates
selection. Preserve exact annual world balance, record the draw and seed, prove
that selection-off still matches the ordinary engine, and do not replace the
hub's explicitly labelled legacy country paths until the paired output passes.
`NEXT_SESSION.md` has the acceptance checklist and scope boundaries.

After that, discuss the next scientific target with Dylan before starting a
finished output. The strongest remaining structural assumption is that the
fertility environment multiplies every propensity type equally, making
selection and environment exactly separable. Testing or relaxing it needs
outside evidence, not a convenient interaction term. Broader cohort-fertility
work from HFD is also valuable per spec section 4.3, but HFD bulk access now
requires an account; the public CFE archive can support some of that work
without a login.

**Do not redesign the public site yet.** Dylan is using the authenticated hub
page as a working document for reviewing figures. The eventual public website
will be redesigned from the ground up and is deliberately out of scope for the
next task.

`NEXT_SESSION.md` carries the rest, including Dylan's editorial direction for
the page and the scoped pieces of it that are not built.

---

*Status confirmed 2026-08-14 on `main` at `299fc2f`; the authenticated hub was
republished after that commit. Last scientific-source audit 2026-08-13: all eight sourced mechanism
parameters verified; `mainstream_propensity_cv` is reproduced from CFE and CDC
cohort data. The Phase 5 grid and map QA were rerun after the corrections, and
all 168 tests pass. Engine validation, Phase 5, and map QA were rerun 2026-08-14;
the full schedule-converter checkpoint was last completed 2026-08-11. The band checks
and headless hover-rendering check all pass. Phases 1 to 5 are complete. The live
page carries the uncertainty band, the hover readout with touch support, the
corrected uncertainty decomposition, the explicit UN boundary, the stochastic
migration-extension figure and the two mechanisms. Phase 4's ensemble is stored
as vintage `2026-08-10-phase4-uw-baseline` with every quantity marked as not a
project claim.*

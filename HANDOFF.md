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
| Any country over 10,000 people | worst **0.07%** | 0.5% |
| Any five-year age group under 100 | worst **0.006%** | 0.05% |
| Open 100+ group | 1.08% | 2% |
| Constant fertility at 2100 vs the UN's own | **0.05%** | 0.5% |

The zero-migration variant is the real test: every input is published, nothing
is tuned, and any discrepancy is our arithmetic being wrong. The medium variant
is reported as a **diagnostic, not a test**, because its migration term is a
residual backed out of the UN's own medium path — see §8.

Output on the UN's assumptions unchanged: world population peaks at **10.29
billion in 2084**, falls to **8.78 billion by 2150**. Constant fertility gives
**53 billion**, which is the absurdity check.

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
adopt by default. It is the **UN-equivalent baseline**, the thing Phase 5 argues
against. The stored vintage marks every quantity `is_project_claim: false`, and
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

## 4. What is not built

- **Phase 5, the mechanistic layer.** Selection and transmission competing with
  a falling fertility environment. This is the project's actual thesis and none
  of it is implemented. `scenarios.py` declares those scenarios with the phase
  that owes them, so the gap is visible in code rather than only in prose;
  asking for one raises.
- **Phase 6, scoring runs.** The formats are fixed and tested, and the Phase 4
  baseline is now stored, but nothing has resolved. The first genuinely
  scoreable quantity is completed cohort fertility for the early-1990s birth
  cohorts, around **2038**.
- **Migration uncertainty in the ensemble.** The engine takes one shared
  migration path, so the band carries fertility and mortality uncertainty only.
  Stated rather than hidden; see §8.
- **Survey coverage and vital-registration completeness** in the confidence
  layer. Only census recency is sourced. Do not invent the other two.
- **A genuinely public host.** The live page is still the authenticated hub.
- **The paper.** `paper/` is an early scaffold written before there were
  results worth writing up, not an approved draft.

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

**Phase 5, the mechanistic layer.** The project's actual thesis, the only part
that can be wrong *diagnostically* rather than numerically, and the reason the
Phase 4 baseline was stored before it existed. Spec section 6 is the design,
section 8 the scenario grid, section 6.10 the anti-epicycle rule. The hard part
is not the code: it is sourcing the parameters independently. Anything that
cannot be is a scenario knob and must be labelled one.

`NEXT_SESSION.md` has the suggested order and the smaller self-contained jobs,
of which the best is cohort fertility from the Human Fertility Database - the
empirical spine of the disagreement with the UN, and the thing that actually
resolves around 2038.


---

*Last verified 2026-08-10: 125 tests pass; engine validation, map QA including
the new band checks, and the schedule-converter checkpoint all pass. Phase 4 is
complete and its ensemble is stored as vintage `2026-08-10-phase4-uw-baseline`.
The map with its uncertainty band is live on the authenticated hub. The
duplicate working copy under `Documents\Codex\` was deleted once its data had
been moved here; this repository is now the only copy.*

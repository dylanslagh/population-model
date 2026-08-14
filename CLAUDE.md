# Working rules for this repo

**Starting cold? Read [HANDOFF.md](HANDOFF.md) first.** It has what is built,
what is verified, and the traps that produce plausible wrong answers rather than
errors. This file is only the rules.

Read `spec/population-2150-spec-v0.3.md` before changing anything. Read section 3
(philosophy) before section 5 (architecture) — several architectural decisions
look wrong if you assume the goal is forecast accuracy. It isn't.

## The standing instructions (spec section 14)

1. **Never fit a mechanism parameter to the series it is meant to explain.** If
   it cannot be sourced independently, mark it a scenario knob — there is a
   `scenario_knobs` field on `Scenario` for exactly this.
2. **Never silently overwrite a stored prediction vintage.** `track.vintage.write`
   raises rather than overwrite. Do not add a `force` flag.
3. **Never treat WPP estimates as ground truth.** Model observation error.
4. **Never score against period TFR.** Cohort fertility only.
5. **Fail loudly on unmatched country codes.** Never drop a country silently.
   The ingest raises on any location code it does not recognise, and on a
   country count that is not exactly 237.
6. **Run prior predictive checks before fitting.** If the prior implies 244
   billion or 300 million, stop.
7. **Do not optimise for forecast accuracy at the expense of structural
   transparency.** That trade is the whole point, and it goes the other way.
8. **Do not make mean reversion the default merely because it is conventional.**

## Conventions this code already commits to

* **Ages** 0–100, where 100 means 100+. **Sex** 0 = female, 1 = male.
* **Populations are people**, not thousands. WPP publishes thousands; the ingest
  multiplies by 1000 exactly once, in `ingest/wpp.py`.
* **Fertility rates are births per woman per year.** WPP publishes per 1000.
* **`sx[a]` is survival INTO age a**, which is the UN's own `Sx` convention.
  `sx[0]` is birth survival. `sx[100]` applies to the sum of the 99-year-olds
  and the existing 100+ group. Read the header of `engine/cohort.py` before
  touching it.
* **Populations are dated 1 January.** Rates supplied for step *t* are the ones
  in force during calendar year *t*.
* **Childbearing ages are 10–54, not 15–49.** WPP's single-age fertility file
  stops at 15–49 and its five-year file does not; the missing mothers are about
  0.3% of world births, which was a visible bias at 2100 before it was fixed.

## Where the line between input and check falls

`ingest/wpp.py` produces engine **inputs**. `ingest/reference.py` produces
**targets** the engine is scored against. Nothing in the engine or in a scenario
may import `reference.py`. Keeping these apart is what stops the project from
quietly testing itself on numbers it was handed.

The same distinction governs migration. The UN does not publish net migrants by
single year of age, so `derive_migration` backs them out of the UN's own medium
path as a residual. That is a usable forward-model input and it is **not**
evidence of anything: any run using it is labelled a diagnostic, not a test.

## Running things

```bash
python scripts/fetch_wpp.py          # ~1.1 GB, once; checksums get committed
python scripts/build_bundle.py       # CSV -> arrays, about 90 seconds
python scripts/validate_engine.py    # the engine test; must pass before anything else
python scripts/run_to_2150.py        # scenarios out to 2150
python -m pytest tests/ -q           # fast, no data needed
```

## Where the project is

Phases 1 to 5 of spec section 10 are done and tested. Phase 6 cannot resolve
before about 2038. Seven of the eight sourced rows in
`data/reference/mechanism_parameters.csv` have now been checked against their
sources; the durable audit is `docs/mechanism-parameter-audit.md`. The remaining
sourced gap is `mainstream_propensity_cv`, which needs completed cohort
family-size data. Five further rows are scenario knobs and cannot be verified by
definition, so Phase 5 magnitudes remain conditional on them. `scenarios.py` declares the unimplemented scenarios
with the phase that owes them, so the gap is visible rather than silent.

The Phase 4 ensemble is the **UN-equivalent baseline**, not this project's own
view of 2150: it propagates UW's mean-reverting posterior, which is the
assumption standing instruction 8 declines to adopt by default. It is stored as
vintage `2026-08-10-phase4-uw-baseline` with every quantity marked
`is_project_claim: false`, so Phase 5 has something fixed to be compared
against.

A correction worth keeping, because it was written down wrong once: archived WPP
revisions are **not** scanned volumes. All fourteen back to 1992 are Excel
workbooks, downloadable from the WPP downloads page under file type "Archive",
and they use the same UN country codes still in use today. If you find a claim
anywhere in this repo that the archives are hard to get, it is stale.

Reading them has two traps. Their internal layout drifts between revisions, so
`ingest/archive.py` locates the header rather than assuming a row number. And
several revisions ship counterfactual scenarios alongside the real projection —
"no AIDS", "instant replacement", "zero migration" — which are excluded by name
in `sources/wpp_archive.py`. Grading a counterfactual as though it were a
forecast would be a serious error, not a rounding problem.

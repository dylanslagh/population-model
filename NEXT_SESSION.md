# Start here in the next session

This is the current, session-specific handoff. Read it before `HANDOFF.md`.
`HANDOFF.md` is the durable technical history; this file records the owner's
goal, what just finished, and the next piece of work.

**Phase 4 is complete.** Phase 5 is the next thing, and it is the one the
project exists for.

## Owner's end goal

Dylan wants two finished public outputs:

1. A genuinely public webpage, not only the current password-gated hub copy.
2. A field-quality research paper in LaTeX and PDF: as close as possible to
   something a person in the field would actually read, while still driven by
   Dylan's vision for the project.

The files under `paper/` are an early scaffold written before there were
results worth writing up. Preserve them, but do not treat their framing as
settled; when the evidence is mature, rewrite rather than polish. The
scientific work comes first.

## Where everything lives

- Repository: `C:\Users\dslag\Documents\GitHub\population-model`. **This is the
  only copy.** A second working copy under `Documents\Codex\` was deleted on
  2026-08-10 once its data had been brought here.
- R, Rtools and Tectonic are large third-party runtimes and still live outside
  the repository. Exact paths: [`LOCAL_TOOLS.md`](LOCAL_TOOLS.md).
- Live page: <https://hub.dylanslagh.com/population-model/>, password-gated.
  No genuinely public host is configured yet.

The map source of truth is `scripts/build_map.py`. The root `index.html` is its
generated, committed output; hand-editing it will not survive a rebuild.

## What Phase 4 produced

UW's Bayesian posterior for fertility and mortality, plus their separate
migration model, propagated through this project's engine one draw at a time.
1,000 draws, 236 countries, 2024 to 2150.

World population: median peaks at **10.31 billion in 2093** and reaches **9.73
billion by 2150**, with a 90% band of **6.97 to 14.36 billion**. 57% of draws
peak before 2100. The map now shows each country's band behind its line.

Two independent checks that were not arranged:

- The deterministic run on the UN's own assumptions peaks at 10.29 billion in
  2084, against the ensemble's 10.31 billion in 2093.
- The deterministic 2100 figure falls inside the ensemble's 5-95% band for
  **97% of countries**. The two runs share only the engine.

**Read this before quoting any of it.** The band is the *UN-equivalent
baseline*. UW's model is mean-reverting, so its long run carries exactly the
assumption standing instruction 8 declines to adopt by default. It is the thing
Phase 5 argues against, not this project's own view of 2150. Every artefact
says so in its own provenance, and the stored vintage marks every quantity
`is_project_claim: false`.

## Do this next: Phase 5, the mechanistic layer

This is the project's actual thesis and none of it is implemented. Spec §6 is
the design; §8 is the scenario grid; §6.10 is the anti-epicycle rule.

The question: selection and transmission raise the share of people disposed to
have more children, while a changing environment lowers how many children any
given disposition produces. The output that matters is **whether and when
selection overtakes the downward environmental shift** — not a better forecast.

Suggested order:

1. **Source the parameters before writing the model.** This is the hard part
   and the part that decides whether the result means anything. Retention,
   intermarriage and fertility differentials for high-fertility subpopulations
   (spec §4.3 item 3); heritability of fertility-related traits, treated as the
   several distinct things §6.2 says it is. Anything that cannot be sourced
   independently is a scenario knob and must be labelled one. **Never fit a
   mechanism parameter to the fertility series it is meant to explain.**
2. **Build group membership as a transition process, not a permanent label**
   (§6.4), with the mainstream as a real population rather than a residual
   bucket (§6.5).
3. **Add the development-pressure term** (§6.9) so the two forces can act at
   once, which is the whole point of the two-axis scenario design in §8.
4. **Run the scenario grid** and compare against the Phase 4 baseline, which is
   already stored and cannot now be adjusted to flatter a mechanism.

`scenarios.py` already declares the unimplemented scenarios with the phase that
owes them; asking for one raises rather than silently returning something.

## Smaller, self-contained work if you want it

- **Cohort fertility from the Human Fertility Database.** The empirical spine
  of the disagreement with the UN, the thing that actually resolves around
  2038, and one genuinely good figure. Spec §4.3 calls it the highest-value
  dataset after WPP.
- Extend the backtest to the 2010-2019 revisions.
- Per-country backtest, which needs a successor-state map for the USSR,
  Yugoslavia, Czechoslovakia, Sudan and Ethiopia.
- Survey coverage or vital-registration completeness in the confidence layer,
  from a real source, as its own dimension rather than folded into a score.

## Known limitations to state, not fix quietly

- **The ensemble excludes migration uncertainty.** The engine takes one shared
  migration path, so the band carries fertility and mortality uncertainty only.
  Widening it means either changing the `propagate` contract or accepting a
  third undocumented index coupling across three separately fitted models.
- **Cross-country pairing is inferred.** Trajectory *k* in every country is
  treated as one posterior sample. That is how bayesTFR generates and bayesPop
  aggregates, but it is not read off UW documentation. It is the most
  load-bearing unverified assumption in the bundle.
- **After 2100 the rates are held constant.** UW stops at 2100; half the
  distance to 2150 rests on our assumption, not theirs.
- **Holy See** is in WPP's 237 and absent from UW's 236, so it is excluded
  rather than invented — about 500 people.

## First checks in a new session

```powershell
python -m pytest tests -q
python scripts\validate_engine.py
python scripts\check_map.py
python scripts\check_schedules.py
```

## Working rules

- Read `CLAUDE.md`, then the relevant parts of `HANDOFF.md` and the spec.
- Fail loudly on unmatched countries or changed source files.
- Never fit a mechanism parameter to the outcome it is meant to explain.
- Keep archives, unpacked objects and build outputs out of git; commit their
  manifests and the readers that reproduce them.
- Work directly on `main`, commit and push after verifying.
- **Rebuild the hub whenever `index.html` changes**:
  `gh workflow run publish.yml --repo dylanslagh/project-hub`. Pushing this
  repository does not do it.

## What Dylan needs to decide later

Nothing is needed to start Phase 5. Before a genuinely public release: the
public hostname and the licensing decision. Before the paper: title, author
line, acknowledgements and release status.

*Updated 2026-08-10, after Phase 4 completed.*

# Start here in the next session

This is the current, session-specific handoff. Read it before `HANDOFF.md`.
`HANDOFF.md` is the durable technical history; this file records the owner's
goal, the machine's actual file locations, what just finished, and the next
piece of work.

## Owner's end goal

Dylan wants two finished public outputs:

1. A genuinely public webpage, not only the current password-gated project-hub
   copy.
2. A field-quality research paper in LaTeX and PDF: as close as possible to
   something a person in the relevant field would actually read, while still
   being driven by Dylan's vision for this project.

The paper should follow the substantive model, tests, and results. The files
already under `paper/` are an early scaffold that was created before Dylan
asked for a paper draft. They are not an approved preliminary paper or a signal
to prioritize paper polishing now. Preserve them, but keep the immediate focus
on the scientific work. When the evidence is mature, replace or substantially
rewrite the scaffold rather than treating its present framing as settled.

## Where the project is

- Repository: `C:\Users\dslag\Documents\GitHub\population-model`
- Branch: `main`
- Current live page: <https://hub.dylanslagh.com/population-model/>
- Hosting status: the current page is behind the project's hub login. A
  genuinely public host has not been configured.

Until 2026-08-10 the project was split across two working copies: this one held
the UN data and the built engine bundle, and a scratch workspace under
`Documents\Codex\` held the 6.2 GB of UW Bayesian data and the pinned R library.
Neither could run phase 4 end to end. The UW data and R library were copied here
and verified against the committed manifest, so this is now the only copy that
matters. See [`LOCAL_TOOLS.md`](LOCAL_TOOLS.md).

The authoritative map source is `scripts/build_map.py`. The root `index.html`
is its generated, committed output. Do not hand-edit `index.html` and expect the
change to survive a rebuild.

For every machine-specific path, including R, Rtools, Tectonic, Python, the UW
archives, the unpacked simulations, and the Finland export, see
[`LOCAL_TOOLS.md`](LOCAL_TOOLS.md).

## What is complete

- The map color bug that began this handoff is fixed and the map checker passes.
- The deterministic cohort projection engine is built and validated against
  WPP 2024.
- The historical UN backtest is built for the 1992--2008 revisions.
- The exact annual UW WPP-aligned TFR and life-expectancy archives are already
  downloaded locally; do not download the 2.24 GB again.
- Both UW archives were checked, fingerprinted, and safely unpacked.
- A project-local R 4.4.2 and Rtools44 installation exists, with pinned
  `bayesTFR` 7.4-4 and `bayesLife` 5.3-0 packages.
- A real 1,000-trajectory Finland fixture was exported through the official R
  package accessors and validated in Python.
- The UW source contains 236 modeled locations. The one WPP location absent
  from it was verified as Holy See, M49 336; do not silently fill it.
- The draw/provenance and one-draw-at-a-time propagation boundaries exist.
- The last full test run passed 86 tests.

The committed provenance receipts are:

- `data/manifest/uw_wpp2024_files.json`
- `data/manifest/uw_wpp2024_finland_fixture.json`

## What is not complete

- UW's compact TFR and female/male life-expectancy trajectories have not yet
  been converted into the age-specific fertility and survival schedules the
  population engine needs.
- There is no real Bayesian population ensemble yet.
- The project's mechanistic fertility layer is not implemented.
- The public webpage has not been moved to a genuinely public production host.
- The current paper is only a scaffold; it is not the intended field-facing
  research paper.

## The decision made on 2026-08-10

Dylan reviewed the state of the project and chose to **finish Phase 4
completely** before starting the mechanistic layer: all 236 locations, a full
ensemble, uncertainty bands on the live map, stored as a scored prediction
vintage. The alternative considered was a deliberately small Phase 4 on about
ten argument-carrying countries, moving to Phase 5 sooner. That was declined.
Discipline first: no mechanism until the baseline is complete and comparable.

One consequence has to stay visible in every write-up. **UW's posterior is a
mean-reverting model.** Importing it imports exactly the long-run assumption
standing instruction 8 tells this project not to adopt by default. The Phase 4
ensemble is therefore the *UN-equivalent baseline* — the thing Phase 5 argues
against — and it must be labelled that way wherever it is published. It is not
this project's own uncertainty about 2150.

## Do this next — the eight steps of Phase 4

1. **One copy of everything.** *(done 2026-08-10.)* UW archives, unpacked
   simulations and the pinned R library now live in this repository and verify
   against `data/manifest/uw_wpp2024_files.json`. A second country, Nigeria
   (566), was exported here through the R accessor to prove the reader works
   from this path.
2. **The fertility converter.** UW supplies one total fertility rate per
   country-year; the engine needs births spread over mothers aged 10-54. Take
   each country's WPP 2024 age shape from the bundle's `asfr`, normalise it, and
   scale it to the drawn rate. State explicitly how the shape behaves after
   2024, and record the rule in provenance rather than leaving it implicit.
3. **The mortality converter.** UW supplies female and male life expectancy; the
   engine needs `sx` at every age. Same relational logic, harder arithmetic: the
   bundle's `sx` gives each country's own age pattern, and the pattern must be
   shifted until it reproduces the drawn life expectancy. Declare the tolerance.
   This is the one genuine modelling decision in Phase 4; everything else is
   engineering.
4. **Prove both on Finland.** Convert the verified 1,000-trajectory fixture and
   show the schedules reconstruct the source TFR and e0 within the declared
   tolerances. Nothing scales until this passes.
5. **Export the remaining 234 locations.** Loop *inside* R. One country at a
   time through `export_uw_fixture.py` takes about 2.5 minutes because it
   reloads the 1.8 GB simulation object every call, which is roughly ten hours
   for the full set; loading once and iterating is the fix. Expect about 1.4 GB
   of exported CSV. Fingerprint the result.
6. **Decide migration out loud.** UW also publishes `bayesMig` trajectories,
   which are not downloaded. Either fetch them or run zero migration, but label
   whichever is chosen; do not reuse the WPP residual and call it probabilistic.
7. **Prior predictive checks** before believing anything, per standing
   instruction 6.
8. **Run the ensemble, store the vintage, put the band on the map.** UW stops at
   2100 and this project runs to 2150. Those last fifty years are an assumption
   of ours, not an inherited one, and must be named in the extension policy and
   on the page.

Do not put the population projection inside the sampler. Do not describe
separately sourced fertility and mortality draws as a joint posterior. Their
component IDs and pairing rule must remain visible.

## First checks in a new session

From the repository root in PowerShell:

```powershell
python -m pytest tests -q
python scripts\check_map.py
python scripts\fetch_uw_posteriors.py --check
python scripts\export_uw_fixture.py --check-only
```

The R installation is deliberately local rather than system-wide. Confirm it
without searching the machine:

```powershell
$rscript = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tools\R-4.4.2\bin\Rscript.exe'
& $rscript --version
```

## Working rules

- Read `CLAUDE.md`, then the relevant parts of `HANDOFF.md` and the model spec.
- Treat `spec/population-2150-spec-v0.3.md` as the design authority, while also
  preserving corrections already documented in `HANDOFF.md`.
- Fail loudly on unmatched countries or changed source files.
- Never fit a mechanism parameter to the outcome it is meant to explain.
- Keep downloaded archives, unpacked source objects, local runtimes, and build
  outputs out of git. Commit their manifests and reproducible readers.
- The normal project workflow is direct work on `main`, with a deliberate
  commit and push after verification.
- Rebuild the separate project hub only when the committed public page changes;
  a documentation-only commit does not require a hub publish.

## What Dylan needs to decide later

Nothing is needed from Dylan to start the schedule converter. Before the truly
public release, ask for the preferred public hostname and the repo/publication
licensing decision. Before the field-facing paper release, confirm title,
author line, acknowledgments, and release status. Those decisions should not
block the current scientific work.

*Updated 2026-08-10.*

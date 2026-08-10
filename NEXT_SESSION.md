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

- Repository: `C:\Users\dslag\Documents\Codex\2026-08-09\i\population-model`
- Workspace: `C:\Users\dslag\Documents\Codex\2026-08-09\i`
- Branch at handoff: `main`
- Commit before this documentation update: `c49213e`
- Current live page: <https://hub.dylanslagh.com/population-model/>
- Hosting status: the current page is behind the project's hub login. A
  genuinely public host has not been configured.

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

## Do this next

Continue Phase 4 by building a separately versioned schedule converter:

1. Define the explicit conversion from annual TFR to age-specific fertility
   rates and from female/male e0 to age-specific survival schedules.
2. Record the conversion method, version, source checksums, and all extension
   assumptions in provenance.
3. Test the conversion first on the verified Finland fixture. Demonstrate that
   the generated schedules reconstruct the compact source quantities within
   declared tolerances.
4. Only after that checkpoint, export all 236 UW locations.
5. Run prior-predictive checks through the existing projection engine before
   fitting or publishing a posterior population range.

Do not put the population projection inside the sampler. Do not describe
separately sourced fertility and mortality draws as a joint posterior. Their
component IDs and pairing rule must remain visible. Migration must be an
explicit assumption, and any extension after UW's 2100 endpoint must be named
and recorded.

## First checks in a new session

From the repository root in PowerShell:

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m pytest tests -q
& $python scripts\check_map.py
& $python scripts\fetch_uw_posteriors.py --check
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

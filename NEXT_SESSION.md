# Start here in the next session

This is the current, session-specific handoff. Read it before `HANDOFF.md`.
`HANDOFF.md` is the durable technical history; this file records the owner's
goal, what just finished, and the next piece of work.

**Phases 1 to 5 are built.** The single highest-value job left is not code: it
is verifying `data/reference/mechanism_parameters.csv` against the literature it
cites. See "Do this next".

## Owner's goal, and his editorial direction

Dylan wants three finished public outputs:

1. **A genuinely public webpage**, not only the password-gated hub copy.
2. **A field-quality research paper.** The files under `paper/` are an early
   scaffold written before there were results worth writing up — preserve them,
   but rewrite rather than polish when the time comes.
3. **A YouTube video**, in the bar-chart-race genre: the twelve most populous
   countries, 1950 to 2100, framed explicitly as the UN's own figures so the
   legitimacy comes from the source rather than from us. His idea, added
   2026-08-11. `scripts/render_race.py` writes the frames.

The video stops at 2100 on purpose: that is where the UN's assumptions stop, and
everything past it is this project's own extrapolation, which does not belong in
something whose credibility rests on the source. Through 2023 the bars are the
UN's reconstruction; from 2024 a whisker appears on each bar and widens, which
is the one thing every other population race video lacks. There is no encoder on
this machine, so the frames are the deliverable and the MP4 is a separate step.

**His view on what earns a reader's trust, which overrode mine and is the better
call.** Not the backtest. Grading old UN forecasts is evidence about somebody
else's model, and leading with it implicitly promises accuracy — a promise spec
section 3.5 explicitly declines to make. What earns trust is showing that the
different *kinds* of uncertainty are represented correctly: relax an assumption,
watch the band widen by the right amount. The backtest still belongs on the page,
but reframed as evidence for that thesis — its best number is that only **41 of
117** world projections landed inside the UN's own low-to-high range, which is a
fact about published ranges being too narrow.

Build in that spirit. Prefer showing the model's own ignorance to showing
somebody else's error.

## Whose opinions are whose

Dylan's global instructions file is his own words, and he prunes anything an
assistant wrote and attributed to him. Apply the same care here: several strong
positions in the spec are assistant reasoning he accepted, not preferences he
holds. `HANDOFF.md` section 2 lists the notable ones. The standing rules in
`CLAUDE.md` are the opposite case and do bind.

## Where everything lives

- Repository: `C:\Users\dslag\Documents\GitHub\population-model`. The only copy.
- R, Rtools and Tectonic live outside it; exact paths in [`LOCAL_TOOLS.md`](LOCAL_TOOLS.md).
- Live page: <https://hub.dylanslagh.com/population-model/>, password-gated.
- The map source of truth is `scripts/build_map.py`; root `index.html` is its
  generated, committed output. **Pushing does not rebuild the hub** —
  `gh workflow run publish.yml --repo dylanslagh/project-hub`.

## What the model now says

**Phase 4, the probabilistic baseline.** UW's posterior propagated through this
project's engine: 1,000 draws, 236 countries, to 2150. Median peaks at 10.31
billion in 2093 and reaches 9.73 billion by 2150, 90% band 6.97 to 14.36. It is
the **UN-equivalent baseline** — a mean-reverting model — not this project's own
view, and the stored vintage marks every quantity `is_project_claim: false`.

**Phase 5, the mechanism.** Selection and transmission against a changing
fertility environment. Against the UN environment, selection adds about 2.1
billion by 2150; continued development pressure removes about 2.4 billion;
together they land at 7.75 billion. **Selection materially offsets continued
pressure and does not overcome it by 2150.** "Never" was always a legitimate
answer and this is close to it.

**The decomposition.** World 90% width at 2150, in billions: fertility 7.26, the
mechanism 5.79, migration 1.75, our own post-2100 hold-constant rule 0.73,
mortality 0.52. Per country at 2100 the ordering reverses — migration is 16.9x
fertility for the UAE and 0.05x for Nigeria. Which uncertainty dominates is a
fact about where you look.

## Do this next

**1. Verify the mechanism parameter table.** `data/reference/mechanism_parameters.csv`
carries thirteen parameters, all marked `verified=FALSE`: they are an assistant's
recollection of the published literature, not values fetched by a script. Five
are scenario knobs with no independent support at all. The mechanism is real and
the architecture is sound; the magnitudes above are illustrative until each row
is checked against the paper it cites and flipped to TRUE. This is mostly
reading, and it is worth more than any further code.

Highest leverage rows: `mainstream_persistence` and `mainstream_propensity_cv`
set how strong selection can be; `development_decline_per_decade` is the single
most important number in the model and cannot be looked up at all.

**2. Cohort fertility from the Human Fertility Database.** Spec section 4.3 calls
it the highest-value dataset after WPP. It is the empirical spine of the
disagreement with the UN, it would let `mainstream_propensity_cv` be measured
rather than recalled, and it resolves around 2038.

**3. Finish the page in Dylan's direction.** Concrete pieces already scoped:
- Per-country uncertainty decomposition, not just the six watch countries. The
  script computes world plus a fixed list; widening it to all 236 is small.
- The violin should drop out below some screen width and let the numeric readout
  carry it, rather than shrinking into illegibility. Only the readout exists.
- Dylan originally imagined the distribution as a **separate panel to the left**
  of the trajectory chart rather than attached to it. Better on desktop; both
  are awkward on a phone.
- The backtest, reframed per his direction above.

**4. Phase 6, scoring.** Formats are ready and two vintages are stored. Nothing
resolves before about 2038; WPP 2027 is the next data event.

## Known limitations to state, not fix quietly

- **The published band contains no migration uncertainty.** One shared migration
  path per run. Worth 1.75bn of world width and most of the answer for the Gulf.
- **Selection and environment are separable** in the Phase 5 model: the
  environment multiplies every type equally, so it cancels out of the relative
  birth weights, and the two full-selection curves coincide exactly. Probably
  wrong — a harsher environment plausibly costs high-propensity people more.
- **Cross-country pairing is inferred.** Trajectory k in every country is treated
  as one posterior sample. That is how bayesTFR generates and bayesPop
  aggregates, but it is not read off UW documentation.
- **After 2100 rates are held constant**, which is ours, not the source's, and
  measured at 0.73bn of extra width.
- **Named groups start with the host country's age structure**, which understates
  their growth. Group shares from Phase 5 are lower bounds.
- **Holy See** is excluded rather than invented — about 500 people.

## First checks in a new session

```powershell
python -m pytest tests -q
python scripts\validate_engine.py
python scripts\check_map.py
python scripts\check_schedules.py
python scripts\run_phase5.py
```

## Working rules

- Read `CLAUDE.md`, then the relevant parts of `HANDOFF.md` and the spec.
- Fail loudly on unmatched countries or changed source files.
- Never fit a mechanism parameter to the outcome it is meant to explain.
- Keep archives and build outputs out of git; commit manifests and readers.
- Work directly on `main`, commit and push after verifying.
- Rebuild the hub whenever `index.html` changes.

## What Dylan needs to decide later

Nothing blocks the work above. Before a genuinely public release: the public
hostname and the licensing decision. Before the paper: title, author line,
acknowledgements and release status.

*Updated 2026-08-11, after Phase 5 and the uncertainty decomposition.*

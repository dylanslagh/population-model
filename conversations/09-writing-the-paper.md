# 09. Writing the paper

**Claude Code** &middot; 2026-08-15 to 2026-08-16 &middot; 2 messages from Dylan, 15 from the model, 218 tool calls.

> Tool output and model reasoning are omitted; see [README](README.md) for what that leaves out and why.

---

### Dylan

Time to work on the paper: Chatgpt did some work on the paper, but that was in the middle of the project, it's ~\Documents\GitHub\population-model\paper if you want to reuse anything, but it needs to be completely rewritten. I think the focus of the paper should be on the updated model with selection applied to the population, that's what I find most scientifically interesting. Below that I would rank: the UN project extension, and the universal depressing parameter (economic pressure, doesn't need to be named as such in the paper, your call) creating the boundary figure and the associated scientific ideas around that. Your work should be scientifically interesting and novel, And focus on being readable to a skilled academic while still being readable by me, I'm non-technical but consider myself a competent reader of scientific literature.

### Model

I'll start by getting oriented — reading the handoff, the spec, and what ChatGPT already wrote.

<details><summary>29 tool calls</summary>

- `Read — ~\Documents\GitHub\population-model\HANDOFF.md`
- `Bash — ls -la "~/Documents/GitHub/population-model/paper" 2>/dev/null && echo "---" && ls "C:/Users/d...`
- `Read — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Bash — cd "~/Documents/GitHub/population-model/paper" && ls -R sections appendices generated bibliogr...`
- `Bash — cd "~/Documents/GitHub/population-model" && ls docs && echo "=== data/reference ===" && ls dat...`
- `Read — ~\Documents\GitHub\population-model\src\popmodel\mech\composition.py`
- `Read — ~\Documents\GitHub\population-model\src\popmodel\mech\environment.py`
- `Bash — cd "~/Documents/GitHub/population-model" && echo "=== mechanism_parameters.csv ===" && cat dat...`
- `Bash — cd "~/Documents/GitHub/population-model" && ls -la out/ 2>/dev/null | head -50 && echo "=== vi...`
- `Read — ~\Documents\GitHub\population-model\src\popmodel\mech\runs.py`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json for f in ['out/un_project_...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('data/ref...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Read — ~\Documents\GitHub\population-model\scripts\analyze_selection_break_even.py`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('data/ref...`
- `Read — ~\Documents\GitHub\population-model\src\popmodel\mech\engine.py`
- `Read — ~\Documents\GitHub\population-model\scripts\build_paper.py`
- `Bash — cd "~/Documents/GitHub/population-model/paper" && echo "=== preamble ===" && cat preamble.tex ...`
- `Bash — cd "~/Documents/GitHub/population-model/paper" && cat sections/01_abstract.tex sections/02_int...`
- `Read — ~\Documents\GitHub\population-model\LOCAL_TOOLS.md`
- `Bash — cd "~/Documents/GitHub/population-model" && wc -l docs/mechanism-parameter-audit.md docs/migra...`
- `Read — ~\Documents\GitHub\population-model\docs\mechanism-parameter-audit.md`
- `Read — ~\Documents\GitHub\population-model\src\popmodel\mech\sensitivity.py`
- `Read — ~\Documents\GitHub\population-model\out\selection-break-even-paired.png`
- `Read — ~\Documents\GitHub\population-model\docs\phase5.png`

</details>

### Model

Now let me verify the literature I want to cite — I won't put a DOI in the bibliography I haven't checked.

<details><summary>26 tool calls</summary>

- `ToolSearch — select:WebSearch,WebFetch`
- `WebSearch — Collins Page heritability of fertility makes world population stabilization unlikely Evolution and Human Be...`
- `WebSearch — Kolk Cownden Enquist correlations in fertility across generations can low fertility persist Proceedings Roy...`
- `WebFetch — https://pmc.ncbi.nlm.nih.gov/articles/PMC10355194/`
- `WebFetch — https://www.sciencedirect.com/science/article/abs/pii/S1090513817302799`
- `WebSearch — Azose Raftery 2015 "Bayesian probabilistic projection of international migration" Demography DOI`
- `WebSearch — Byars Ewbank Govindaraju Stearns "Natural selection in a contemporary human population" PNAS 2010 Framingham`
- `WebFetch — https://www.jasoncollins.blog/posts/an-evolutionary-projection-of-global-fertility-and-population-my-new-pa...`
- `WebSearch — Burger Oskar DeLong John "What if fertility decline is not permanent evolutionarily informed approach low f...`
- `WebFetch — https://blog.jcx.au/posts/an-evolutionary-projection-of-global-fertility-and-population-my-new-paper-with-l...`
- `WebSearch — Ševčíková Raftery bayesPop "Probabilistic Population Projection" Journal of Statistical Software 2016 DOI`
- `WebSearch — Gerland 2014 Science "World population stabilization unlikely this century" DOI volume pages; Vollset 2020 ...`
- `WebSearch — Kong 2017 PNAS "Selection against variants in the genome associated with educational attainment" DOI; Beauc...`
- `WebSearch — Price 1970 Nature "Selection and covariance" 227 520 DOI 10.1038; Robertson 1966 "mathematical model of the...`
- `WebSearch — Lutz Skirbekk Testa "low fertility trap hypothesis" Vienna Yearbook of Population Research 2006 DOI pages`
- `Bash — cd "~/Documents/GitHub/population-model" && python -c " import json d=json.load(open('out/phas...`
- `Read — ~\Documents\GitHub\population-model\scripts\run_phase5.py`
- `Bash — cd "~/Documents/GitHub/population-model" && cat out/phase5_run.log | tail -30 && echo "=== dec...`
- `Bash — cd "~/Documents/GitHub/population-model" && ls data/processed/ 2>/dev/null && echo "--- venv -...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/run_phase5.py -...`
- `Read — ~\Documents\GitHub\population-model\docs\migration-extension.md`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "OUT\|json.dump\|write_text\|LIMIT\|limit"...`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -25 out/phase5_paper_run.log && echo "=== ens...`
- `Bash — cd "~/Documents/GitHub/population-model" && ls -la out/phase5.json && git status --short && gi...`
- `Bash — cd "~/Documents/GitHub/population-model" && git show 9243d01 --stat && echo "=== engine diff =...`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "migration\|maximum\|clip\|negative" src/p...`

</details>

### Model

`run_phase5.py` is broken on `main` — a strict feasibility check added for the stochastic migration policy also fires on the plain-array path, which the ordinary engine deliberately clips. Fixing that first, since the paper's numbers have to be regenerable.

<details><summary>8 tool calls</summary>

- `Edit — ~\Documents\GitHub\population-model\src\popmodel\mech\engine.py`
- `Edit — ~\Documents\GitHub\population-model\src\popmodel\mech\engine.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/run_phase5.py -...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json for f ...`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -24 out/phase5_paper_run.log`
- `Read — ~\AppData\Local\Temp\claude\<project-scratch>\fd025039-0589-460...`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "stop-at-2090\|post_2100\|0.73\|hold" scri...`

</details>

### Model

Now the results-macro generator, so no headline number is typed into the prose by hand.

<details><summary>14 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -25 out/phase5_paper_run.log 2>/dev/null; ech...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json d=json...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json b=json...`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -24 out/phase5_paper_run.log && echo "=== con...`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/build_paper_res...`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\run_phase5.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/run_phase5.py -...`
- `Read — ~\Documents\GitHub\population-model\scripts\plot_paired_selection_boundary.py`
- `Write — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -6 out/phase5_paper_run.log && ./.venv/Script...`
- `Read — ~\AppData\Local\Temp\claude\<project-scratch>\fd025039-0589-460...`

</details>

### Model

Phase 5 is still running. Writing the manuscript now, starting with the verified bibliography.

<details><summary>11 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\paper\bibliography\references.bib`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/build_paper_res...`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig1-mechanism.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig2-ladder.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig4-boundary-2100.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig5-decomposition.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig3-boundary.png`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import numpy as np...`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`

</details>

### Model

Now the 2100-boundary figure, using the stored annual paths rather than three interpolated points.

<details><summary>14 tool calls</summary>

- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Bash — cd "~/Documents/GitHub/population-model" && sed -i 's| figure_boundary_2100(phase5, load("data...`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig4-boundary-2100.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig5-decomposition.png`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/plot_paper_figu...`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig5-decomposition.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig1-mechanism.png`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/plot_paper_figu...`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig5-decomposition.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig2-ladder.png`

</details>

### Model

Figures are clean. Now the manuscript.

<details><summary>14 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\paper\metadata.tex`
- `Write — ~\Documents\GitHub\population-model\paper\preamble.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\01_abstract.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\02_introduction.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\03_mechanism.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\04_calibration.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\05_engine.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\06_results.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json; d=jso...`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/build_paper_res...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`

</details>

### Model

Now the boundary section — the paper's central result.

<details><summary>2 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\paper\sections\07_boundary.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json d=json...`

</details>

### Model

The separability is near-exact rather than exact — migration and age structure break it slightly. Correcting that claim.

<details><summary>5 tool calls</summary>

- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Edit — ~\Documents\GitHub\population-model\paper\sections\07_boundary.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\08_horizon.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json d=json...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import json d=json...`

</details>

### Model

Found a mislabelled field in the ensemble writer — it reports a mean under the name `median_peak`. Fixing it, and dropping a claim from the paper I can't regenerate.

<details><summary>6 tool calls</summary>

- `Bash — cd "~/Documents/GitHub/population-model" && sed -n '275,286p' scripts/run_uw_ensemble.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\run_uw_ensemble.py`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "world\[:, peak_index\]\|peak_index\|quant...`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "^\s*world\s*=\|world =" scripts/run_uw_en...`
- `Edit — ~\Documents\GitHub\population-model\scripts\run_uw_ensemble.py`
- `Edit — ~\Documents\GitHub\population-model\paper\sections\08_horizon.tex`

</details>

### Model

Now the discussion, limitations and conclusion.

<details><summary>22 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\paper\sections\09_discussion.tex`
- `Write — ~\Documents\GitHub\population-model\paper\sections\10_conclusion.tex`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Edit — ~\Documents\GitHub\population-model\scripts\build_paper_results.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/build_paper_res...`
- `Write — ~\Documents\GitHub\population-model\paper\appendices\a_parameters.tex`
- `Write — ~\Documents\GitHub\population-model\paper\appendices\b_reproducibility.tex`
- `Write — ~\Documents\GitHub\population-model\paper\main.tex`
- `Bash — cd "~/Documents/GitHub/population-model/paper" && rm -f sections/03_data_backtest.tex sections...`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`
- `Read — ~\Documents\GitHub\population-model\paper\build\main.pdf`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " try: import fitz; ...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -c " import fitz d=fitz...`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-01.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-02.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-04.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-05.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-11.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-13.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-24.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-25.png`

</details>

### Model

Table 4 overflows the margin and the institutional citations render at full length. Fixing both.

<details><summary>36 tool calls</summary>

- `Edit — ~\Documents\GitHub\population-model\paper\appendices\b_reproducibility.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`
- `Edit — ~\Documents\GitHub\population-model\paper\preamble.tex`
- `Edit — ~\Documents\GitHub\population-model\paper\appendices\a_parameters.tex`
- `Edit — ~\Documents\GitHub\population-model\paper\appendices\b_reproducibility.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`
- `Bash — cd "~/Documents/GitHub/population-model" && rm -rf out/paper-pages && ./.venv/Scripts/python.e...`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-14.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-17.png`
- `Edit — ~\Documents\GitHub\population-model\scripts\plot_paper_figures.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/plot_paper_figu...`
- `Read — ~\Documents\GitHub\population-model\out\paper-figures\fig4-boundary-2100.png`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-03.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-07.png`
- `Edit — ~\Documents\GitHub\population-model\paper\sections\02_introduction.tex`
- `Edit — ~\Documents\GitHub\population-model\paper\sections\04_calibration.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && grep -n "commensurable" paper/sections/*.tex`
- `Edit — ~\Documents\GitHub\population-model\paper\sections\02_introduction.tex`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-19.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-23.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-12.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-21.png`
- `Edit — ~\Documents\GitHub\population-model\paper\appendices\a_parameters.tex`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`
- `Bash — cd "~/Documents/GitHub/population-model" && rm -rf out/paper-pages && ./.venv/Scripts/python.e...`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-22.png`
- `Read — ~\Documents\GitHub\population-model\out\paper-pages\page-27.png`
- `Edit — ~\Documents\GitHub\population-model\paper\appendices\a_parameters.tex`
- `Read — ~\Documents\GitHub\population-model\paper\index.html`
- `Write — ~\Documents\GitHub\population-model\paper\index.html`
- `Write — ~\Documents\GitHub\population-model\paper\README.md`
- `Bash — cd "~/Documents/GitHub/population-model" && export TECTONIC='~\Documents\Codex\20...`

</details>

### Model

Now verifying the whole repo still passes its own checks before committing.

<details><summary>4 tool calls</summary>

- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -m pytest tests/test_pa...`
- `Read — ~\Documents\GitHub\population-model\tests\test_paper.py`
- `Bash — cd "~/Documents/GitHub/population-model" && cat paper/bibliography/source-audit.csv`

</details>

### Model

The two failures are guardrails written for the old scaffold. Replacing them with tests that enforce the rules the new paper actually keeps.

<details><summary>27 tool calls</summary>

- `Write — ~\Documents\GitHub\population-model\paper\bibliography\source-audit.csv`
- `Write — ~\Documents\GitHub\population-model\tests\test_paper.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -m pytest tests/test_pa...`
- `Edit — ~\Documents\GitHub\population-model\tests\test_paper.py`
- `Edit — ~\Documents\GitHub\population-model\tests\test_paper.py`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1...`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe scripts/check_map.py 2>...`
- `Edit — ~\Documents\GitHub\population-model\HANDOFF.md`
- `Edit — ~\Documents\GitHub\population-model\HANDOFF.md`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -12 HANDOFF.md`
- `Edit — ~\Documents\GitHub\population-model\HANDOFF.md`
- `Bash — cd "~/Documents/GitHub/population-model" && ./.venv/Scripts/python.exe - <<'PY' from pathlib i...`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Bash — cd "~/Documents/GitHub/population-model" && tail -5 NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\NEXT_SESSION.md`
- `Edit — ~\Documents\GitHub\population-model\LOCAL_TOOLS.md`
- `Bash — cd "~/Documents/GitHub/population-model" && git status --short && echo "=== gitignore check ==...`
- `Bash — cd "~/Documents/GitHub/population-model" && git check-ignore -v paper/build/main.pdf 2>&1 || e...`
- `Bash — cd "~/Documents/GitHub/population-model" && git add -A && git commit -q -F - <<'MSG' && git lo...`
- `Bash — cd "~/Documents/GitHub/population-model" && git push 2>&1 | tail -5 && echo "=== rebuild hub =...`
- `SendUserFile`
- `Bash — cd "~/Documents/GitHub/population-model" && sleep 45; gh run list --repo dylanslagh/project-hu...`

</details>

### Model

The paper is written, built, committed, pushed, and the hub is rebuilt — it's live at `hub.dylanslagh.com/population-model/paper/`.

## What the paper argues

**Title:** *Selection on Fertility, and the Environmental Decline That Would Cancel It* — 27 pages, ten sections, two appendices, five figures.

The order follows your ranking. Selection leads, the boundary is how selection gets made quantitative, and the UN project extension is the section that draws the 2100 line.

The spine of the argument:

1. **Conventional projections model a national rate, which has no composition in it.** Family size is dispersed (CV 0.57) and imperfectly transmitted (parent–child correlation 0.15), so the parents of each generation are sampled in proportion to how many children they have. That's selection, its direction on fertility is always upward, and it's absent from the standard machinery by construction. Worth **1.82 billion people at 2150**.

2. **Named groups are a small part of the story.** Haredi and Amish contribute **2.5%** of what unlabelled mainstream variation contributes — even though the model is generous to them at every choice point. This inverts how the subject usually gets discussed, and I foregrounded it.

3. **The headline is the boundary, not a number.** Because selection and the environment both multiply fertility, they're commensurable, so the unmeasurable parameter gets reported as the threshold where it cancels measured selection: **1.52% per decade**. That turns "what will the population be" into "how fast would conditions have to keep deteriorating," which is a rate someone could argue about.

Two things I did that strengthen the novelty claim. The literature already has Collins & Page (2019) arguing heritable fertility makes stabilisation unlikely, and Arenberg et al. (2022) in *Demography* replying that a model built from transmission alone has no absolute fertility level in it and therefore can't establish growth. Your model answers that critique structurally — it carries the UN's absolute age-specific rates at every step — and it lands in the middle: the mechanism is real and large, and it is *not* a return to growth. That's a genuine position, not a hedge. Every citation was checked against the publisher's record; where I couldn't confirm a page range, I left it out rather than guess.

## Three things I fixed along the way

- **`run_phase5.py` was broken on `main`.** The strict migration-feasibility check from commit `9243d01` was firing on the plain-array path as well as the stochastic policy. The policy must raise; a plain array is the UN's own residual and `engine/cohort.py` clips it, so the typed engine has to clip too or it stops reproducing the untyped one exactly — which is the check that makes the whole attribution argument work.
- **`run_uw_ensemble.py` reported a mean under the name `median_peak`** (10.36 vs the actual median 10.31). Both are now written under their own names.
- **A claim in the repo is overstated.** `plot_phase5.py`'s footnote and both handoff files say the two full-selection curves coincide *exactly*. They don't — 1.176 vs 1.174, a 0.22% gap, because a harsher environment changes the age structure and changes how forcefully a fixed migrant count mixes in. The paper states this correctly; the figure footnote still doesn't, and I left the figure alone rather than quietly editing a chart you've already reviewed.

## What's enforced rather than promised

No headline number is typed into the prose. `scripts/build_paper_results.py` writes 146 macros and the parameter table from committed result files and refuses to build on a missing key or an out-of-bounds value. `tests/test_paper.py` reads the headline values back out and fails if any appears as a literal in a section file. Those two tests replaced the old ones that checked the scaffold *admitted* to being unfinished — that guard became unenforceable the moment the paper was finished, so I replaced it rather than deleted it. 173 tests pass; engine validation and `check_map` pass.

## What's yours to decide

Title wording, the author line (currently "Dylan Slagh, independent researcher, Atlanta" with no affiliation), acknowledgements, the licence, and whether and where this gets released. I flagged these in `paper/README.md` rather than leaving TODOs in the document.

One judgement call worth naming: I dropped the "97% of countries" agreement statistic from the comparator section because it's printed by `check_map.py` but not stored in a result file the paper reads, and I wouldn't put a number in that the build can't regenerate. The peak comparison replaced it. If you want it back, it's a small change to have `check_map.py` write it out.

### Dylan

can you put your earlier critiques into a .md in the repo for later?


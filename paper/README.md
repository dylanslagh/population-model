# Research paper

**Selection on Fertility, and the Environmental Decline That Would Cancel It.**
A compositional mechanism inside a validated 237-country projection to 2150.

Version 1.0.0, written 2026-08-15. This replaced the earlier scaffold that was
written before there were results worth writing up; nothing of its prose
survives, and the framing it used ("research design and preliminary backtest")
is superseded.

## What the paper argues

Conventional long-run projections model the national fertility rate as a
mean-reverting time series, which has no composition in it. Family size is
dispersed and imperfectly transmitted, so the parents of each generation are
sampled in proportion to how many children they have, and the composition drifts
upward. The paper measures that force, shows it is worth 1.82 billion people at
2150, shows that named high-fertility groups contribute only 2.5% of it, and
then reports a **break-even boundary** rather than a preferred total: the
additional environmental decline (1.52% per decade after 2050) that would
exactly cancel measured selection.

## Build

```powershell
$env:TECTONIC = 'C:\Users\dslag\Documents\Codex\2026-08-09\i\work\tectonic-0.17.0\tectonic.exe'
.\.venv\Scripts\python.exe scripts\build_paper_results.py   # macros + parameter table
.\.venv\Scripts\python.exe scripts\plot_paper_figures.py    # figures, PDF + review PNG
.\.venv\Scripts\python.exe scripts\build_paper.py           # -> paper/build/main.pdf
.\.venv\Scripts\python.exe scripts\build_paper.py --publish # -> paper/population-model.pdf
```

`build_paper.py` never reruns the model. If a result file is stale, regenerate it
with the script named in `appendices/b_reproducibility.tex` and rerun
`build_paper_results.py`.

**Look at the pages before publishing.** `--publish` is not a substitute for
review. The pattern used here is to rasterise every page and open it:

```powershell
.\.venv\Scripts\python.exe -c "import pymupdf,pathlib; d=pymupdf.open('paper/build/main.pdf'); o=pathlib.Path('out/paper-pages'); o.mkdir(parents=True,exist_ok=True); [p.get_pixmap(dpi=105).save(o/f'page-{i+1:02d}.png') for i,p in enumerate(d)]"
```

The same applies to figures: `plot_paper_figures.py` writes a PNG beside every
PDF into `out/paper-figures/` for exactly this reason.

## Rules this directory keeps

- **No headline result is typed into prose.** Every number comes through a macro
  in `generated/results_macros.tex`, written by `scripts/build_paper_results.py`
  from a result file. The generator raises on a missing file, a missing key, or
  a value outside a stated sanity bound.
- **The parameter table is generated too**, straight from
  `data/reference/mechanism_parameters.csv`, so it cannot drift from the values
  the model ran with.
- **A 2150 result is always accompanied by its assumptions** — fertility,
  mortality, migration, and the post-2100 extension rule.
- **WPP estimates are comparison data, not ground truth.**
- **Bibliographic details are checked against primary sources before use.** Where
  a volume or page range could not be confirmed, it is omitted rather than
  guessed; the DOI identifies the work.
- **Figures for the paper carry no titles.** The caption does that job. Review
  figures in `docs/` are separate and do carry their own titles, because they
  are looked at alone.

## Layout

| Path | What it is |
|---|---|
| `main.tex` | Document, section order, bibliography style |
| `metadata.tex`, `preamble.tex` | Title block and packages |
| `sections/` | Ten section files, numbered in reading order |
| `appendices/a_parameters.tex` | Parameter table plus its sources |
| `appendices/b_reproducibility.tex` | What produced each number, and the conventions |
| `generated/` | Machine-written macros and the parameter table |
| `figures/` | Vector PDFs used by the manuscript |
| `bibliography/references.bib` | Checked entries only |
| `index.html` | The landing page, kept in step with the paper |
| `population-model.pdf` | The reviewed, published PDF |

## Decisions still owned by Dylan

Title wording, the author line and affiliation, acknowledgements, the licence,
and whether and where this is released. The paper currently carries an
independent-researcher author line with no affiliation and no acknowledgements
section.

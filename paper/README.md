# Research paper

This directory is the living manuscript for the project's second public
output. The interactive webpage is the exploratory companion; the paper is the
formal account of the evidence, model, assumptions, results, and predetermined
tests.

The current manuscript is deliberately labelled an analysis protocol with
preliminary evidence. Its backtest and deterministic-engine sections are
supported by results already in the repository. It becomes a conventional
working paper only after the probabilistic and mechanism-comparison analyses
exist and pass their checks.

## Build

Install Tectonic, or a LaTeX distribution that supplies `pdflatex` and
`bibtex`, then run:

```powershell
python scripts\build_paper.py
```

`TECTONIC`, `PDFLATEX`, and `BIBTEX` environment variables can point the build
at executables that are not on the normal command path.

That writes the candidate PDF to `paper/build/main.pdf`. Render and inspect
every page before copying it to the stable public path:

```powershell
python scripts\build_paper.py --publish
```

The publish option is not a substitute for visual review. A reviewed
`paper/population-model.pdf` is tracked so the webpage and a branch preview show
the exact paper being evaluated, not a PDF rebuilt differently by a server.

## Rules

- No headline result is typed into prose if it can be generated from a result
  file.
- The webpage and paper must share figures, tables, and result values.
- A 2150 result is always accompanied by its fertility, mortality, migration,
  and post-2100 extension assumptions.
- UW fertility and mortality samples are not described as a joint posterior
  unless a joint model is actually fitted.
- WPP estimates are comparison data, not ground truth.
- Unsupported future sections stay visibly marked as unfinished.
- Bibliographic details are checked against primary sources before use.

`bibliography/source-audit.csv` records which source supports each important
claim and whether that source has been checked.

# Research paper

> **Owner direction, 2026-08-10:** this directory is an early scaffold created
> before Dylan asked for a paper draft. It is not an approved preliminary paper
> or a current project milestone. Preserve it, but do not prioritize paper
> polishing before the substantive model, tests, and results exist. The final
> goal is still a field-quality research paper in LaTeX and PDF, written for a
> relevant scholarly audience and driven by Dylan's project vision.

The current files are useful as build infrastructure and as a possible starting
point. Their framing and prose are not settled. A future agent should
substantially rewrite or replace them after the probabilistic and
mechanism-comparison analyses exist and pass their checks.

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

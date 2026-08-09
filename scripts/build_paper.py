"""Compile the LaTeX working paper without regenerating scientific results.

    python scripts/build_paper.py
    python scripts/build_paper.py --publish

The candidate always lands in paper/build/main.pdf. ``--publish`` additionally
copies that candidate to the tracked stable path after the caller has reviewed
the rendered pages. Scientific results and figures are built separately; this
command never downloads data or reruns the model implicitly.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAPER = REPO / "paper"
BUILD = PAPER / "build"
MAIN = PAPER / "main.tex"
STABLE = PAPER / "population-model.pdf"


def executable(name: str) -> str:
    override = os.environ.get(name.upper())
    found = override or shutil.which(name)
    if not found:
        raise SystemExit(
            f"{name} was not found. Install a LaTeX distribution, then rerun."
        )
    return found


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=PAPER, check=True)


def build_with_tectonic(tectonic: str) -> Path:
    run([
        tectonic,
        "--keep-logs",
        "--keep-intermediates",
        "--outdir",
        str(BUILD),
        str(MAIN),
    ])
    return BUILD / "main.pdf"


def build_with_pdftex() -> Path:
    pdflatex = executable("pdflatex")
    bibtex = executable("bibtex")
    latex = [
        pdflatex,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-output-directory={BUILD}",
        str(MAIN),
    ]
    run(latex)
    run([bibtex, str(BUILD / "main")])
    run(latex)
    run(latex)
    return BUILD / "main.pdf"


def build() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    tectonic = os.environ.get("TECTONIC") or shutil.which("tectonic")
    candidate = build_with_tectonic(tectonic) if tectonic else build_with_pdftex()
    if not candidate.exists() or candidate.stat().st_size == 0:
        raise SystemExit("LaTeX completed without producing paper/build/main.pdf")
    log = (BUILD / "main.log").read_text(encoding="utf-8", errors="replace")
    blg_path = BUILD / "main.blg"
    blg = blg_path.read_text(encoding="utf-8", errors="replace") if blg_path.exists() else ""
    bbl_path = BUILD / "main.bbl"
    bbl = bbl_path.read_text(encoding="utf-8", errors="replace") if bbl_path.exists() else ""
    if "There were undefined citations" in log or "undefined references" in log:
        raise SystemExit("LaTeX left unresolved citations or references; see paper/build/main.log")
    if "error message" in blg.lower() or "\\bibitem" not in bbl:
        raise SystemExit("BibTeX did not produce a complete bibliography; see paper/build/main.blg")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="copy the candidate to paper/population-model.pdf after review",
    )
    args = parser.parse_args()
    candidate = build()
    print(f"Built {candidate.relative_to(REPO)}")
    if args.publish:
        shutil.copy2(candidate, STABLE)
        print(f"Published {STABLE.relative_to(REPO)}")
    else:
        print("Render and inspect every page before using --publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

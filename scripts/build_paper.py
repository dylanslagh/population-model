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
SUPPLEMENT = PAPER / "supplement.tex"
STABLE = PAPER / "population-model.pdf"
STABLE_SUPPLEMENT = PAPER / "population-model-supplement.pdf"
VERSIONED = PAPER / "population-model-1_2_0.pdf"
VERSIONED_SUPPLEMENT = PAPER / "population-model-supplement-1_2_0.pdf"


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


def build_with_tectonic(tectonic: str, source: Path) -> Path:
    run([
        tectonic,
        "--keep-logs",
        "--keep-intermediates",
        "--outdir",
        str(BUILD),
        str(source),
    ])
    return BUILD / f"{source.stem}.pdf"


def build_with_pdftex(source: Path) -> Path:
    pdflatex = executable("pdflatex")
    bibtex = executable("bibtex")
    latex = [
        pdflatex,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-output-directory={BUILD}",
        str(source),
    ]
    run(latex)
    run([bibtex, str((BUILD / source.stem).relative_to(PAPER))])
    run(latex)
    run(latex)
    return BUILD / f"{source.stem}.pdf"


def build_one(source: Path) -> Path:
    tectonic = os.environ.get("TECTONIC") or shutil.which("tectonic")
    candidate = (
        build_with_tectonic(tectonic, source) if tectonic
        else build_with_pdftex(source)
    )
    stem = source.stem
    if not candidate.exists() or candidate.stat().st_size == 0:
        raise SystemExit(f"LaTeX completed without producing paper/build/{stem}.pdf")
    log = (BUILD / f"{stem}.log").read_text(encoding="utf-8", errors="replace")
    blg_path = BUILD / f"{stem}.blg"
    blg = blg_path.read_text(encoding="utf-8", errors="replace") if blg_path.exists() else ""
    bbl_path = BUILD / f"{stem}.bbl"
    bbl = bbl_path.read_text(encoding="utf-8", errors="replace") if bbl_path.exists() else ""
    if "There were undefined citations" in log or "undefined references" in log:
        raise SystemExit(f"unresolved citations or references; see paper/build/{stem}.log")
    if "error message" in blg.lower() or "\\bibitem" not in bbl:
        raise SystemExit(f"BibTeX produced no complete bibliography; see paper/build/{stem}.blg")
    return candidate


def build() -> list[tuple[Path, tuple[Path, ...]]]:
    """Build the paper and its supplement, in that order.

    Both are built every time. A supplement that silently stops compiling while
    the paper still does is a way to publish a paper whose appendix references
    point at nothing.
    """
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    return [
        (build_one(MAIN), (STABLE, VERSIONED)),
        (build_one(SUPPLEMENT), (STABLE_SUPPLEMENT, VERSIONED_SUPPLEMENT)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="copy the candidates to their stable paths after review",
    )
    args = parser.parse_args()
    for candidate, destinations in build():
        print(f"Built {candidate.relative_to(REPO)}")
        if args.publish:
            for destination in destinations:
                shutil.copy2(candidate, destination)
                print(f"Published {destination.relative_to(REPO)}")
    if not args.publish:
        print("Render and inspect every page before using --publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The research paper remains buildable, explicit, and source-audited."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from popmodel import paths

PAPER = paths.REPO_ROOT / "paper"


def test_main_manuscript_includes_every_declared_section():
    main = (PAPER / "main.tex").read_text(encoding="utf-8")
    section_files = sorted((PAPER / "sections").glob("*.tex"))
    appendix_files = sorted((PAPER / "appendices").glob("*.tex"))
    assert len(section_files) >= 9
    for path in section_files + appendix_files:
        relative = path.relative_to(PAPER).with_suffix("").as_posix()
        assert f"\\input{{{relative}}}" in main


def test_unfinished_scientific_sections_say_they_are_unfinished():
    baseline = (PAPER / "sections" / "05_probabilistic_baseline.tex").read_text(
        encoding="utf-8"
    )
    mechanisms = (PAPER / "sections" / "06_mechanisms.tex").read_text(
        encoding="utf-8"
    )
    assert "\\wip{" in baseline
    assert "\\wip{" in mechanisms
    assert "not be described as a joint fertility-mortality posterior" in baseline
    assert "No mechanism has been fitted" in mechanisms


def test_source_audit_is_complete_and_points_to_bibliography_entries():
    bibliography = (PAPER / "bibliography" / "references.bib").read_text(
        encoding="utf-8"
    )
    bib_keys = set(re.findall(r"@[a-zA-Z]+\{([^,]+),", bibliography))
    with (PAPER / "bibliography" / "source-audit.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) >= 8
    assert all(row["claim"] and row["location"] and row["verified_on"] for row in rows)
    assert {row["citation_key"] for row in rows} <= bib_keys
    assert all(row["status"] == "verified" for row in rows)


def test_latex_sources_use_portable_ascii_text():
    for path in PAPER.rglob("*.tex"):
        content = path.read_text(encoding="utf-8")
        assert content.isascii(), f"non-ASCII text in {path.relative_to(paths.REPO_ROOT)}"

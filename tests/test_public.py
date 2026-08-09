"""The public build exposes only reviewed artifacts and never broken links."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from popmodel import paths

SCRIPT = paths.REPO_ROOT / "scripts" / "build_public.py"
SPEC = importlib.util.spec_from_file_location("build_public", SCRIPT)
assert SPEC and SPEC.loader
build_public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_public)


def make_repo(tmp_path: Path, html: str | None = "<!doctype html><title>Map</title>") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    if html is not None:
        (repo / "index.html").write_text(html, encoding="utf-8")
    return repo


def add_paper(repo: Path, landing: str = "<!doctype html><h1 id='abstract'>Paper</h1>") -> None:
    paper = repo / "paper"
    paper.mkdir(exist_ok=True)
    (paper / "index.html").write_text(landing, encoding="utf-8")
    (paper / "population-model.pdf").write_bytes(b"%PDF-1.7\nreviewed fixture\n")


def staged_paths(output: Path) -> set[str]:
    return {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }


def test_build_stages_only_the_reviewed_root_page_and_clears_stale_output(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("not public", encoding="utf-8")
    output = repo / "dist"
    output.mkdir()
    (output / "stale.txt").write_text("old build", encoding="utf-8")

    files = build_public.build(repo, output)

    assert [path.relative_to(output).as_posix() for path in files] == ["index.html"]
    assert staged_paths(output) == {"index.html"}


def test_build_stages_the_paper_only_as_a_complete_reviewed_pair(tmp_path):
    repo = make_repo(tmp_path, "<a href='paper/#abstract'>Read the paper</a>")
    add_paper(repo, "<h1 id='abstract'>Paper</h1><a href='population-model.pdf#page=1'>PDF</a>")

    build_public.build(repo)

    assert staged_paths(repo / "dist") == {
        "index.html",
        "paper/index.html",
        "paper/population-model.pdf",
    }


@pytest.mark.parametrize("present", ["landing", "pdf"])
def test_build_rejects_a_half_published_paper(tmp_path, present):
    repo = make_repo(tmp_path)
    paper = repo / "paper"
    paper.mkdir()
    if present == "landing":
        (paper / "index.html").write_text("<title>Paper</title>", encoding="utf-8")
    else:
        (paper / "population-model.pdf").write_bytes(b"%PDF-1.7\n")

    with pytest.raises(build_public.BuildError, match="paper publication is incomplete"):
        build_public.build(repo)


def test_build_requires_a_nonempty_root_index(tmp_path):
    missing = make_repo(tmp_path, html=None)
    with pytest.raises(build_public.BuildError, match="required public artifact is missing: index.html"):
        build_public.build(missing)


def test_build_rejects_a_broken_local_resource_without_leaving_partial_output(tmp_path):
    repo = make_repo(tmp_path, "<img src='assets/missing.png' alt='missing fixture'>")

    with pytest.raises(
        build_public.BuildError, match=r"(?s)broken local link.*assets/missing\.png"
    ):
        build_public.build(repo)

    assert not (repo / "dist").exists()


def test_build_rejects_a_broken_html_fragment(tmp_path):
    repo = make_repo(tmp_path, "<a href='paper/#results'>Results</a>")
    add_paper(repo)

    with pytest.raises(build_public.BuildError, match=r"missing fragment #results"):
        build_public.build(repo)


def test_external_links_data_urls_and_valid_root_links_do_not_require_files(tmp_path):
    repo = make_repo(
        tmp_path,
        "<main id='top'><a href='https://example.org'>Source</a>"
        "<img src='data:image/gif;base64,AAAA' alt='fixture'></main>",
    )
    add_paper(repo, "<a href='/#top'>Back to map</a>")

    build_public.build(repo)

    assert staged_paths(repo / "dist") == {
        "index.html",
        "paper/index.html",
        "paper/population-model.pdf",
    }


def test_build_rejects_a_non_pdf_at_the_reviewed_pdf_path(tmp_path):
    repo = make_repo(tmp_path)
    add_paper(repo)
    (repo / "paper" / "population-model.pdf").write_text("not a PDF", encoding="utf-8")

    with pytest.raises(build_public.BuildError, match="reviewed paper is not a PDF"):
        build_public.build(repo)


def test_build_refuses_to_replace_any_directory_other_than_repo_dist(tmp_path):
    repo = make_repo(tmp_path)

    with pytest.raises(build_public.BuildError, match="refusing unsafe output directory"):
        build_public.build(repo, tmp_path / "somewhere-else")

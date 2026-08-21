"""Stage the small, reviewed public surface of the repository.

    python scripts/build_public.py

The model inputs and intermediate outputs are intentionally not deployable. This
command copies only the committed public pages -- the scrollytelling front page,
the interactive map, and, once both exist, the paper's landing page with its
reviewed PDFs -- into ``dist/``. It then checks every local HTML link against
that staged tree. A missing required file, a half-published paper, or a broken
local link stops the build.

The versioned PDF filenames are read from the paper's own generated results, so
a new version cannot leave the landing page pointing at a file nobody staged.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"

INDEX = Path("index.html")
MAP = Path("map/index.html")
SOCIAL_CARD_SOURCE = Path("site/social-card.jpg")
SOCIAL_CARD = Path("social-card.jpg")
AUTHOR_PORTRAIT_SOURCE = Path("site/author-dylan.webp")
AUTHOR_PORTRAIT = Path("authors/dylan-slagh.webp")
ANTHROPIC_MARK_SOURCE = Path("site/anthropic.svg")
ANTHROPIC_MARK = Path("authors/anthropic.svg")
OPENAI_MARK_SOURCE = Path("site/openai.svg")
OPENAI_MARK = Path("authors/openai.svg")
PAPER_LANDING = Path("paper/index.html")
PAPER_PDF = Path("paper/population-model.pdf")
PAPER_SUPPLEMENT = Path("paper/population-model-supplement.pdf")
PAPER_MACROS = Path("paper/generated/results_macros.tex")


class BuildError(RuntimeError):
    """A public artifact is missing, unsafe, or internally inconsistent."""


class LinkCollector(HTMLParser):
    """Collect local-resource candidates and anchors from one HTML document."""

    LINK_ATTRIBUTES = {
        "a": ("href",),
        "area": ("href",),
        "audio": ("src",),
        "form": ("action",),
        "iframe": ("src",),
        "img": ("src", "srcset"),
        "input": ("src",),
        "link": ("href",),
        "object": ("data",),
        "script": ("src",),
        "source": ("src", "srcset"),
        "track": ("src",),
        "use": ("href",),
        "video": ("src", "poster"),
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        if "id" in values:
            self.anchors.add(values["id"])
        if tag.lower() == "a" and "name" in values:
            self.anchors.add(values["name"])

        for attribute in self.LINK_ATTRIBUTES.get(tag.lower(), ()):
            value = values.get(attribute)
            if value is None:
                continue
            if attribute == "srcset":
                if value.lstrip().lower().startswith("data:"):
                    continue
                for candidate in value.split(","):
                    url = candidate.strip().split(maxsplit=1)[0]
                    if url:
                        self.links.append((attribute, url))
            else:
                self.links.append((attribute, value.strip()))


def _required_source(repo: Path, relative: Path) -> Path:
    path = repo / relative
    if path.is_symlink():
        raise BuildError(f"required public artifact may not be a symlink: {relative.as_posix()}")
    if not path.is_file():
        raise BuildError(f"required public artifact is missing: {relative.as_posix()}")
    if path.stat().st_size == 0:
        raise BuildError(f"required public artifact is empty: {relative.as_posix()}")
    return path


def _paper_version(repo: Path) -> str | None:
    """The version the paper build stamped, as it appears in PDF filenames."""

    macros = repo / PAPER_MACROS
    if not macros.is_file():
        return None
    found = re.search(r"\\newcommand\{\\PaperVersion\}\s*\{([^}]+)\}",
                      macros.read_text(encoding="utf-8"))
    return found.group(1).strip().replace(".", "_") if found else None


def reviewed_sources(repo: Path) -> list[tuple[Path, Path]]:
    """Return the exact source/destination allowlist for this public build."""

    sources = [
        (_required_source(repo, INDEX), INDEX),
        (_required_source(repo, MAP), MAP),
        (_required_source(repo, SOCIAL_CARD_SOURCE), SOCIAL_CARD),
        (_required_source(repo, AUTHOR_PORTRAIT_SOURCE), AUTHOR_PORTRAIT),
        (_required_source(repo, ANTHROPIC_MARK_SOURCE), ANTHROPIC_MARK),
        (_required_source(repo, OPENAI_MARK_SOURCE), OPENAI_MARK),
    ]
    landing = repo / PAPER_LANDING
    pdf = repo / PAPER_PDF
    paper_parts = (landing.is_file(), pdf.is_file())
    if any(paper_parts) and not all(paper_parts):
        missing = PAPER_PDF if paper_parts[0] else PAPER_LANDING
        raise BuildError(
            "paper publication is incomplete: "
            f"{missing.as_posix()} is missing; publish the landing page and reviewed PDF together"
        )
    if all(paper_parts):
        landing = _required_source(repo, PAPER_LANDING)
        pdf = _required_source(repo, PAPER_PDF)
        with pdf.open("rb") as stream:
            signature = stream.read(5)
        if signature != b"%PDF-":
            raise BuildError(f"reviewed paper is not a PDF: {PAPER_PDF.as_posix()}")
        sources.extend(((landing, PAPER_LANDING), (pdf, PAPER_PDF)))
        supplement = repo / PAPER_SUPPLEMENT
        if supplement.is_file():
            sources.append((_required_source(repo, PAPER_SUPPLEMENT), PAPER_SUPPLEMENT))
        version = _paper_version(repo)
        if version:
            for stem in ("population-model", "population-model-supplement"):
                relative = Path(f"paper/{stem}-{version}.pdf")
                sources.append((_required_source(repo, relative), relative))
    return sources


def _parse_html(path: Path) -> LinkCollector:
    parser = LinkCollector()
    try:
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
    except (OSError, UnicodeError) as error:
        raise BuildError(f"cannot read staged HTML {path.name}: {error}") from error
    return parser


def _local_target(root: Path, document: Path, raw_url: str) -> tuple[Path, str] | None:
    """Resolve one browser URL into the staged tree, or return None if external."""

    if not raw_url:
        return document, ""
    parsed = urlsplit(raw_url)
    if parsed.scheme or parsed.netloc:
        return None

    url_path = unquote(parsed.path)
    if "\\" in url_path:
        raise BuildError(f"local link uses a backslash: {raw_url!r}")

    document_relative = document.relative_to(root).as_posix()
    if not url_path:
        normalized = document_relative
    elif url_path.startswith("/"):
        normalized = posixpath.normpath(url_path.lstrip("/") or ".")
    else:
        normalized = posixpath.normpath(
            posixpath.join(posixpath.dirname(document_relative), url_path)
        )
    if normalized == ".." or normalized.startswith("../"):
        raise BuildError(f"local link escapes the public root: {raw_url!r}")

    target = root if normalized == "." else root.joinpath(*PurePosixPath(normalized).parts)
    if url_path.endswith("/") or target.is_dir():
        target /= "index.html"
    return target, unquote(parsed.fragment)


def check_local_links(root: Path) -> None:
    """Raise when any staged HTML resource or fragment link is unresolved."""

    documents = sorted({*root.rglob("*.html"), *root.rglob("*.htm")})
    parsed = {document: _parse_html(document) for document in documents}
    failures: list[str] = []
    for document, page in parsed.items():
        source = document.relative_to(root).as_posix()
        for attribute, raw_url in page.links:
            try:
                resolved = _local_target(root, document, raw_url)
            except BuildError as error:
                failures.append(f"{source} {attribute}={raw_url!r}: {error}")
                continue
            if resolved is None:
                continue
            target, fragment = resolved
            if not target.is_file():
                missing = target.relative_to(root).as_posix()
                failures.append(f"{source} {attribute}={raw_url!r}: missing {missing}")
                continue
            if fragment and target.suffix.lower() in {".html", ".htm"}:
                target_page = parsed.get(target) or _parse_html(target)
                if fragment not in target_page.anchors:
                    failures.append(
                        f"{source} {attribute}={raw_url!r}: missing fragment #{fragment}"
                    )

    if failures:
        detail = "\n  ".join(failures)
        raise BuildError(f"broken local link(s):\n  {detail}")


def build(repo: Path = REPO, output: Path | None = None) -> list[Path]:
    """Stage and validate the allowlisted public files, replacing output atomically."""

    repo = repo.resolve()
    expected_output = repo / "dist"
    output = Path(os.path.abspath(output or expected_output))
    if output != expected_output or output.is_symlink():
        raise BuildError(f"refusing unsafe output directory: {output}")

    sources = reviewed_sources(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        for source, relative in sources:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        check_local_links(temporary)

        if output.exists():
            if output.is_symlink() or not output.is_dir():
                raise BuildError(f"refusing to replace non-directory output: {output}")
            shutil.rmtree(output)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

    return [output / relative for _, relative in sources]


def main() -> int:
    try:
        files = build()
    except BuildError as error:
        print(f"Public build failed: {error}", file=sys.stderr)
        return 1
    print(f"Staged {len(files)} reviewed file(s) in {DIST.relative_to(REPO)}/")
    for path in files:
        print(f"  {path.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

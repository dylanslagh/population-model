"""Assemble the public site into one self-contained page.

    python scripts/build_site.py

Reads ``site/index.template.html``, ``site/body.html``, ``site/app.js`` and the
two data files from ``scripts/build_site_assets.py``, and writes ``index.html``
at the repository root. One file, no build step for the browser, no external
requests except the web font and the embedded video: the same reasoning as the
map page, which is that every dependency is a liability over a horizon this
project claims to care about.

**Every number printed on the page is checked here.** Any element carrying a
``data-v`` attribute names a path into ``site/data/story.json``; the text inside
it must agree with the value stored there, or this build fails. That is what
stops the prose drifting away from the results while nobody is looking.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
OUT = REPO / "index.html"

TOKENS = {
    "<!--#BODY#-->": SITE / "body.html",
    "<!--#SCRIPT#-->": SITE / "app.js",
}


class BuildError(RuntimeError):
    """The page and the results disagree, or a part of the page is missing."""


def resolve(data, path: str):
    """Walk a dotted path, where a numeric part indexes a list."""
    node = data
    for part in path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        else:
            if part not in node:
                raise BuildError(f"data-v=\"{path}\" does not exist in story.json")
            node = node[part]
    return node


def as_number(raw: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-−]", "", raw.replace("−", "-"))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def check_numbers(body: str, story: dict) -> int:
    """Compare every data-v element's text with the value it names."""
    pattern = re.compile(
        r"<(?P<tag>\w+)(?P<attrs>[^>]*\bdata-v=\"(?P<path>[^\"]+)\"[^>]*)>(?P<text>[^<]*)</(?P=tag)>"
    )
    checked = 0
    problems: list[str] = []
    for match in pattern.finditer(body):
        path = match.group("path")
        attrs = match.group("attrs")
        shown = match.group("text").strip()
        stored = resolve(story, path)

        fmt = re.search(r'data-fmt="([^"]+)"', attrs)
        dp = re.search(r'data-dp="(\d+)"', attrs)

        if isinstance(stored, str):
            expected_text = stored
            if shown.replace("−", "-") != expected_text.replace("−", "-"):
                problems.append(f'  {path}: page says "{shown}", results say "{expected_text}"')
            checked += 1
            continue

        value = float(stored)
        if fmt and fmt.group(1) == "millions":
            value = value / 1e6
        shown_number = as_number(shown)
        if shown_number is None:
            problems.append(f'  {path}: "{shown}" is not a number')
            checked += 1
            continue
        places = int(dp.group(1)) if dp else len(shown.partition(".")[2].strip("%"))
        if abs(round(value, places) - shown_number) > 10 ** -(places + 3):
            problems.append(
                f"  {path}: page says {shown}, results say {round(value, places)}"
            )
        checked += 1

    if problems:
        raise BuildError(
            "the page disagrees with the results it is built from:\n"
            + "\n".join(problems)
            + "\n\nEither the prose is stale or the results moved. Fix the page."
        )
    return checked


def main() -> int:
    template = (SITE / "index.template.html").read_text(encoding="utf-8")
    story_path = SITE / "data" / "story.json"
    globe_path = SITE / "data" / "globe.json"
    for path in (story_path, globe_path):
        if not path.exists():
            raise BuildError(
                f"{path.relative_to(REPO)} is missing.\n"
                f"  Run:  python scripts/build_site_assets.py"
            )
    story = json.loads(story_path.read_text(encoding="utf-8"))

    body = TOKENS["<!--#BODY#-->"].read_text(encoding="utf-8")
    checked = check_numbers(body, story)
    print(f"  {checked} printed numbers agree with the results")

    page = template
    for token, source in TOKENS.items():
        if token not in page:
            raise BuildError(f"the template has no {token} slot")
        page = page.replace(token, source.read_text(encoding="utf-8"))
    page = page.replace("<!--#GLOBE#-->", globe_path.read_text(encoding="utf-8"))
    page = page.replace("<!--#STORY#-->", story_path.read_text(encoding="utf-8"))

    if "<!--#" in page:
        leftover = re.findall(r"<!--#\w+#-->", page)
        raise BuildError(f"unfilled slots remain: {leftover}")

    OUT.write_text(page, encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(REPO)} ({OUT.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"\nbuild_site: {error}", file=sys.stderr)
        raise SystemExit(1) from error

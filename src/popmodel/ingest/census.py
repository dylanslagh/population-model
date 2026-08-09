"""Parse the UNSD census-date page into one number per country.

The page is a grid of Bootstrap divs rather than a table: each country is a
`<div class="row">` holding six `<div class="col-md-2">` cells - the name, then
one cell per census round. Two things in the markup will quietly wreck a naive
parse:

* Footnote markers live inside the name cell as `<sup>(3)</sup>`, so stripping
  tags without removing them first turns "Denmark" into "Denmark (3)" and it
  stops matching anything.
* A date in parentheses is a census that is PLANNED, not one that happened.
  Reading "(2031)" as a census year would credit a country for counting its
  people seven years from now.

Matching to WPP is by name, which this project otherwise avoids - the geometry
crosswalk joins on the UN numeric code precisely so it never has to. There is
no code on this page, so names are all there is. The mitigation is the same as
everywhere else: normalise, keep an explicit override table, and raise on
anything left over rather than dropping it.
"""

from __future__ import annotations

import html as html_module
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from popmodel import paths
from popmodel.sources import fetch, unsd_census

# Anything at or before this is outside the earliest round the page covers, so
# "no census since 1985" is the strongest statement the source supports.
EARLIEST_ROUND_START = 1985


class CensusParseError(RuntimeError):
    """The page is not shaped the way this parser expects."""


@dataclass(frozen=True)
class CensusRecord:
    unsd_name: str
    last_census_year: int | None
    rounds: dict[str, str]


def _clean(cell_html: str) -> str:
    """Cell text with footnote markers and section headings removed.

    The first country of each continent shares its row with the section
    heading - the "ASIA / Countries or areas" block sits inside Afghanistan's
    own name cell, and the round labels sit inside its date cells. Strip those
    first or the continent's first country is lost and its dates are read as
    the round's year range.
    """
    text = re.sub(r'<div class="headline">.*?</div>', " ", cell_html, flags=re.S | re.I)
    text = re.sub(r"<sup>.*?</sup>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html_module.unescape(text).split())


def parse(html: str, *, min_rows: int = 100, min_records: int = 180) -> list[CensusRecord]:
    """Parse the page. The two minimums are a guard against a silent layout
    change: the real page has ~236 countries, so a parse that suddenly returns
    forty of them has broken rather than found forty countries. Tests lower
    them to exercise the parsing itself."""
    chunks = html.split('<div class="row">')[1:]
    if len(chunks) < min_rows:
        raise CensusParseError(
            f"only {len(chunks)} rows found; the page layout has changed"
        )

    records: list[CensusRecord] = []
    for chunk in chunks:
        cells = [
            _clean(c)
            for c in re.findall(
                r'<div class="col-md-2"[^>]*>(.*?)(?=<div class="col-md-2"|</div>\s*</div>|$)',
                chunk,
                re.S,
            )
        ]
        if len(cells) < 5:
            continue
        name = cells[0]
        if "Countries or areas" in name or name.isupper():
            continue  # a section header on its own

        # A row whose name cell is blank, or which starts with a dash, is a
        # CONTINUATION of the country above it. Countries that ran two censuses
        # in one round get a second row for the later dates, and the United
        # Kingdom's own row is empty because its censuses are listed under
        # "- England and Wales", "- Scotland" and "- Northern Ireland".
        # Dropping these rows loses the most recent census for exactly the
        # countries that count most often: it had Finland at 1995, Malta at
        # 2005 and the UK at never.
        if (not name or name.startswith("-")) and records:
            previous = records[-1]
            merged = _merge_year(previous.last_census_year, _last_year(cells[1:6]))
            records[-1] = CensusRecord(
                unsd_name=previous.unsd_name,
                last_census_year=merged,
                rounds={**previous.rounds,
                        **{r: c for r, c in zip(unsd_census.ROUNDS, cells[1:6]) if c}},
            )
            continue
        if not name:
            continue

        rounds = dict(zip(unsd_census.ROUNDS, cells[1:6]))
        records.append(
            CensusRecord(unsd_name=name, last_census_year=_last_year(cells[1:6]), rounds=rounds)
        )

    if len(records) < min_records:
        raise CensusParseError(f"only {len(records)} countries parsed; expected ~230")
    return records


def _merge_year(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _last_year(cells: list[str]) -> int | None:
    """Most recent year of a census that actually happened."""
    best = None
    for cell in cells:
        # Parenthesised entries are planned, or "(...)" for unknown.
        if "(" in cell and ")" in cell:
            continue
        for year in re.findall(r"\b(19\d\d|20\d\d)\b", cell):
            year = int(year)
            if best is None or year > best:
                best = year
    return best


def _normalise(name: str) -> str:
    """Lowercase, strip accents and punctuation, and un-invert 'X, Y of'."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    if "," in text:
        head, _, tail = text.partition(",")
        tail = tail.strip()
        # "palestine, state of" -> "state of palestine"
        if tail.endswith(" of") or tail in ("the", "republic of", "state of"):
            text = f"{tail} {head}".strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = ["saint" if w in ("st", "ste") else w for w in text.split()]
    return " ".join(words)


def match_to_wpp(records: list[CensusRecord], countries: pd.DataFrame) -> pd.DataFrame:
    """One row per WPP country. Raises if a country is unaccounted for."""
    wpp_by_norm = {_normalise(n): n for n in countries["Location"]}
    overrides = {_normalise(k): v for k, v in unsd_census.NAME_OVERRIDES.items()}

    resolved: dict[str, CensusRecord] = {}
    unmatched: list[str] = []
    for rec in records:
        norm = _normalise(rec.unsd_name)
        target = overrides.get(norm) or wpp_by_norm.get(norm)
        if target is None:
            unmatched.append(rec.unsd_name)
            continue
        resolved.setdefault(target, rec)

    rows = []
    missing = []
    for _, c in countries.iterrows():
        name = c["Location"]
        rec = resolved.get(name)
        if rec is None:
            if name in unsd_census.NOT_LISTED:
                rows.append((int(c["LocID"]), c["ISO3_code"], name, None,
                             "not listed", unsd_census.NOT_LISTED[name]))
                continue
            missing.append(name)
            continue
        year = rec.last_census_year
        rows.append((int(c["LocID"]), c["ISO3_code"], name, year,
                     _band(year), rec.unsd_name))

    if missing:
        raise CensusParseError(
            f"{len(missing)} WPP countries have no census record and no recorded "
            f"reason:\n  " + "\n  ".join(missing[:30]) +
            "\n\nAdd a spelling to unsd_census.NAME_OVERRIDES, or if UNSD genuinely "
            "does not list the country, add it to NOT_LISTED with the reason. "
            "Do not drop it: a map that silently omits the weakest-data countries "
            "is the opposite of what this layer is for."
        )

    return pd.DataFrame(
        rows,
        columns=["loc_id", "iso3", "name", "last_census_year", "band", "source_name"],
    ).sort_values("loc_id").reset_index(drop=True)


def _band(year: int | None) -> str:
    if year is None:
        return "none since 1985"
    age = 2024 - year
    if age <= 5:
        return "within 5 years"
    if age <= 14:
        return "5 to 14 years"
    return "15 years or more"


def raw_path() -> Path:
    return paths.RAW / "unsd" / "census_dates.html"


def load(countries: pd.DataFrame) -> pd.DataFrame:
    html = fetch.census_page().read_text(encoding="utf-8", errors="replace")
    return match_to_wpp(parse(html), countries)


def table_path() -> Path:
    return paths.REFERENCE / "census_dates.csv"


def load_table() -> pd.DataFrame:
    """The committed census table. Build it with scripts/build_census.py."""
    path = table_path()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing. Run: python scripts/build_census.py"
        )
    return pd.read_csv(path)

"""Read the UN's old revisions out of their Excel workbooks.

These files span thirty years of changing spreadsheet conventions. The 1994
population workbook puts its header on row 15 and its years on row 16; the 1994
life-expectancy workbook puts the header on row 14 and has no variant column at
all; later revisions move things again. So nothing here assumes a fixed layout.
The reader looks for the row containing "country code", takes the row below it
as the year header, and starts reading data below that. If it cannot find those
things it raises rather than guessing, because a silently mis-parsed vintage
would produce a plausible-looking wrong grade.

Two quirks of the old files worth knowing:

* Population is given for single years (1995, 2000, 2005, ...) but fertility
  and life expectancy are given for five-year PERIODS ("2015-2020"). A period
  rate has to be compared against the average of the modern annual series over
  the same years, not against a single year.
* Values are in thousands, as they still are today.

Requires xlrd, which reads the old binary .xls format. It is in the "archive"
optional dependency group so the rest of the project does not carry it.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from popmodel import paths
from popmodel.sources import fetch, wpp_archive

THOUSANDS_TO_PEOPLE = 1000.0
WORLD_CODE = 900

_YEAR = re.compile(r"^\s*(\d{4})(?:\.0)?\s*$")
_PERIOD = re.compile(r"^\s*(\d{4})\s*[-‐-―]\s*(\d{4})\s*$")


class ArchiveError(RuntimeError):
    """An archived workbook is not shaped the way the reader expects."""


@dataclass(frozen=True)
class Series:
    """One quantity from one vintage, as a tidy table.

    `frame` has columns loc_id, year, value. For period quantities it also has
    period_start and period_end, and `year` is the midpoint rounded down.
    """

    vintage: int
    quantity: str
    variant: str
    is_period: bool
    frame: pd.DataFrame


def _open_sheet(zf: zipfile.ZipFile, member: str, wanted: tuple[str, ...]):
    import xlrd

    book = xlrd.open_workbook(file_contents=zf.read(member))
    names = {n.strip().upper(): n for n in book.sheet_names()}
    for candidate in wanted:
        if candidate.strip().upper() in names:
            return book.sheet_by_name(names[candidate.strip().upper()])
    raise ArchiveError(
        f"{member}: none of {wanted} among sheets {book.sheet_names()}"
    )


def _find_member(
    zf: zipfile.ZipFile, patterns: list[str], exclude: list[str], vintage: int
) -> str:
    names = [n for n in zf.namelist() if not n.endswith("/")]
    kept = [n for n in names if not any(x.upper() in n.upper() for x in exclude)]
    for pat in patterns:
        hits = [n for n in kept if pat.upper() in n.upper()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ArchiveError(
                f"WPP{vintage}: pattern {pat!r} matched {len(hits)} files, so the "
                f"reader cannot tell which is meant: {hits}"
            )
    raise ArchiveError(
        f"WPP{vintage}: no workbook matching any of {patterns} "
        f"(after excluding {exclude}). {len(names)} files in the archive."
    )


def _parse_header(sheet) -> tuple[int, int, list[tuple[int, int, int]]]:
    """Locate the header, the country-code column, and the year columns.

    Returns (first_data_row, code_col, [(col, period_start, period_end), ...]).
    A single-year column comes back with start == end.
    """
    header_row = code_col = None
    for r in range(min(60, sheet.nrows)):
        for c, val in enumerate(sheet.row_values(r)):
            if isinstance(val, str) and val.strip().lower() in ("country code", "country  code", "code"):
                header_row, code_col = r, c
                break
        if header_row is not None:
            break
    if header_row is None:
        raise ArchiveError("no row containing 'country code' in the first 60 rows")

    # The year labels sit on the header row itself or the row below it.
    for candidate in (header_row + 1, header_row):
        cols = _year_columns(sheet, candidate, code_col)
        if len(cols) >= 3:
            return candidate + 1, code_col, cols
    raise ArchiveError(f"no year columns found near header row {header_row}")


def _year_columns(sheet, row: int, code_col: int) -> list[tuple[int, int, int]]:
    if row >= sheet.nrows:
        return []
    out = []
    for c in range(code_col + 1, sheet.ncols):
        raw = sheet.cell_value(row, c)
        text = str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw)
        m = _PERIOD.match(text)
        if m:
            out.append((c, int(m.group(1)), int(m.group(2))))
            continue
        m = _YEAR.match(text)
        if m:
            y = int(m.group(1))
            if 1900 <= y <= 2200:
                out.append((c, y, y))
    return out


def _read_sheet(sheet, scale: float) -> tuple[pd.DataFrame, bool]:
    first_row, code_col, year_cols = _parse_header(sheet)
    is_period = any(s != e for _, s, e in year_cols)

    records = []
    for r in range(first_row, sheet.nrows):
        code = sheet.cell_value(r, code_col)
        if isinstance(code, str):
            code = code.strip()
            if not code:
                continue
            try:
                code = float(code)
            except ValueError:
                continue
        if not isinstance(code, (int, float)) or code <= 0:
            continue
        loc = int(round(code))
        for c, start, end in year_cols:
            v = sheet.cell_value(r, c)
            if isinstance(v, str):
                v = v.strip().replace(",", "")
                if v in ("", "...", "-", ".."):
                    continue
                try:
                    v = float(v)
                except ValueError:
                    continue
            if not isinstance(v, (int, float)) or not np.isfinite(v):
                continue
            records.append((loc, start, end, (start + end) // 2, float(v) * scale))

    if not records:
        raise ArchiveError("sheet parsed but produced no data rows")
    df = pd.DataFrame(records, columns=["loc_id", "period_start", "period_end", "year", "value"])
    return df.drop_duplicates(subset=["loc_id", "period_start", "period_end"], keep="first"), is_period


def read_series(key: str, quantity: str, variant: str = "medium") -> Series:
    """Pull one quantity out of one archived revision."""
    rev = wpp_archive.REVISIONS[key]
    patterns, exclude = wpp_archive.WORKBOOK_PATTERNS[quantity]
    scale = THOUSANDS_TO_PEOPLE if quantity == "population" else 1.0

    sheets = {
        "medium": wpp_archive.MEDIUM_SHEETS,
        "low": wpp_archive.LOW_SHEETS,
        "high": wpp_archive.HIGH_SHEETS,
        "estimates": wpp_archive.ESTIMATE_SHEETS,
    }[variant]
    # Life-expectancy workbooks changed shape mid-catalogue. Up to 2004 one
    # workbook holds all three sexes on separate sheets and carries estimates
    # and projections together. From 2006 the sexes are separate workbooks and
    # the sheets are the familiar ESTIMATES/MEDIUM pair. Try both.
    if quantity == "life_expectancy":
        sheets = ("BOTH-SEXES", "BOTH SEXES", "BOTH") + wpp_archive.MEDIUM_SHEETS

    with zipfile.ZipFile(fetch.archive_path(key)) as zf:
        member = _find_member(zf, patterns, exclude, rev.year)
        sheet = _open_sheet(zf, member, sheets)
        frame, is_period = _read_sheet(sheet, scale)

    return Series(vintage=rev.year, quantity=quantity, variant=variant,
                  is_period=is_period, frame=frame)


def cache_path(key: str, quantity: str, variant: str) -> Path:
    return paths.PROCESSED / "archive" / f"{key}_{quantity}_{variant}.csv"


def load_series(key: str, quantity: str, variant: str = "medium", *, refresh: bool = False) -> Series:
    """Same as read_series, but caches the parse. The .xls reading is slow."""
    p = cache_path(key, quantity, variant)
    if p.exists() and not refresh:
        frame = pd.read_csv(p)
        return Series(
            vintage=wpp_archive.REVISIONS[key].year,
            quantity=quantity,
            variant=variant,
            is_period=bool((frame["period_start"] != frame["period_end"]).any()),
            frame=frame,
        )
    s = read_series(key, quantity, variant)
    p.parent.mkdir(parents=True, exist_ok=True)
    s.frame.to_csv(p, index=False)
    return s

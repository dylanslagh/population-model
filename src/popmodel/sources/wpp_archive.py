"""The UN's own back catalogue: every past revision of World Population Prospects.

This is the raw material for spec phase 1, the backtest harness, and it turns
out to be far more available than the spec assumed. Fourteen revisions from
1992 to 2022 are published as Excel workbooks at

    https://population.un.org/wpp/downloads  ->  file type "Archive"

Not scans. Real spreadsheets, with the same UN country codes still in use in
2024, which means a 1994 projection for Kenya can be lined up against a 2024
estimate for Kenya with no fuzzy matching at all.

Why this matters more than the forward model
--------------------------------------------
A projection made in 1994 for the year 2020 is a prediction whose answer is now
known. There are thirty years of these lying around, made by the same
institution using successive versions of the same modelling approach, and
nobody has ever gone back and graded them systematically. That grade is the
thing spec section 9 calls the actual contribution.

Every vintage in here is a bet somebody placed and then stopped talking about.

Sizes and what is worth taking
------------------------------
The old revisions are small and the recent ones are enormous - WPP 2022 alone
is 6.6 GB - but the old ones are also the useful ones, because more of what
they predicted has already happened. A 1992 projection can be graded over 32
years; a 2019 projection over 5, which teaches almost nothing.

So the default set stops at 2008. Later revisions are declared but not
downloaded unless asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

_BASE = "https://population.un.org/wpp/assets/Excel%20Files/5_Archive"
SOURCE_PAGE = "https://population.un.org/wpp/downloads"
URLS_READ_ON = "2026-08-08"


@dataclass(frozen=True)
class ArchivedRevision:
    """One past revision of WPP."""

    year: int  # the revision year, e.g. 1994
    approx_mb: int
    base_year: int  # last year of estimates; everything after is a projection
    in_default_set: bool

    @property
    def key(self) -> str:
        return f"wpp{self.year}"

    @property
    def filename(self) -> str:
        return f"WPP{self.year}-Excel-files.zip"

    @property
    def url(self) -> str:
        return f"{_BASE}/{self.filename}"

    def horizon(self, target_year: int) -> int:
        """How many years ahead a projection for `target_year` was looking."""
        return target_year - self.base_year


# Base years are the revision's own last estimate year. The UN's convention is
# that a revision published in year N has estimates through roughly N-1 or N-2;
# these are the values printed in each workbook's own header, and the ingest
# checks them against the sheets rather than trusting this table.
REVISIONS: dict[str, ArchivedRevision] = {
    r.key: r
    for r in [
        ArchivedRevision(1992, 4, 1990, True),
        ArchivedRevision(1994, 3, 1990, True),
        ArchivedRevision(1996, 6, 1995, True),
        ArchivedRevision(2000, 31, 2000, True),
        ArchivedRevision(2002, 61, 2000, True),
        ArchivedRevision(2004, 149, 2005, True),
        ArchivedRevision(2006, 131, 2005, True),
        ArchivedRevision(2008, 206, 2010, True),
        # Declared but not fetched by default: large, and too recent to grade
        # over a useful horizon.
        ArchivedRevision(2010, 383, 2010, False),
        ArchivedRevision(2012, 393, 2010, False),
        ArchivedRevision(2015, 431, 2015, False),
        ArchivedRevision(2017, 659, 2015, False),
        ArchivedRevision(2019, 690, 2020, False),
        ArchivedRevision(2022, 6632, 2021, False),
    ]
}

DEFAULT_KEYS = [k for k, r in REVISIONS.items() if r.in_default_set]

# Which workbook inside each zip holds what. File names drift a lot between
# revisions - the 1994 zip is flat, the 2008 zip has 520 members in nested
# folders - so these are patterns matched case-insensitively against the zip
# listing rather than exact names. The ingest raises if a pattern matches zero
# files or more than one, so an ambiguity shows up as an error rather than as a
# silently-wrong file.
#
# The exclusions matter. Several revisions ship a parallel "no-AIDS" scenario,
# which is a counterfactual (what if the epidemic had not happened) and would
# be a serious mistake to grade as if it were a forecast. Others split life
# expectancy by sex and by starting age.

# Alternative scenarios shipped alongside the real projection. Every one of
# these is a counterfactual or a deliberate absurdity - what if AIDS had not
# happened, what if fertility instantly jumped to replacement, what if nobody
# migrated - and grading one as though it were a forecast would be a serious
# error, not a rounding problem. They are excluded by name.
SCENARIO_MARKERS = [
    "NO_AIDS", "NO-AIDS", "AIDS_SCENARIO", "AIDS-SCENARIO", "HIGH-AIDS",
    "AIDS-VACCINE", "_AIDS_", "INSTANT-REPLACEMENT", "ZERO-MIGRATION",
    "CONSTANT-MORTALITY", "CONSTANT-FERTILITY", "CONSTANT_FERTILITY",
    "NO-CHANGE", "MOMENTUM", "_IR_", "_ZM_", "_CM_", "_NC_",
]

WORKBOOK_PATTERNS = {
    "population": (
        ["TOTAL_POPULATION_BOTH_SEXES", "TOTAL_POPULATION-BOTH_SEXES"],
        SCENARIO_MARKERS + ["BY_AGE", "PERCENTAGE"],
    ),
    "tfr": (
        ["TOTAL_FERTILITY_TFR", "TOTAL_FERTILITY"],
        SCENARIO_MARKERS + ["BY_AGE"],
    ),
    "life_expectancy": (
        ["LIFE_EXPECTANCY_0", "LIFE_EXPECTANCY_BOTH", "LIFE_EXPECTANCY"],
        SCENARIO_MARKERS + ["BY_AGE", "_MALE", "_FEMALE", "LIFE_EXPECTANCY_15",
                            "LIFE_EXPECTANCY_60", "LIFE_EXPECTANCY_80"],
    ),
}

# The sheet holding the medium-variant projection, and the one holding
# estimates. Some revisions capitalise differently.
MEDIUM_SHEETS = ("MEDIUM", "MEDIUM VARIANT", "Medium")
ESTIMATE_SHEETS = ("ESTIMATES", "ESTIMATE", "Estimates")
LOW_SHEETS = ("LOW", "LOW VARIANT", "Low")
HIGH_SHEETS = ("HIGH", "HIGH VARIANT", "High")

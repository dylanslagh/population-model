"""World Population Prospects 2024 — the pinned source files.

Spec section 4.1: pin to a revision explicitly and make the version a
first-class field in every stored output. That is what REVISION below is for;
nothing in this project should ever say "the UN data" without saying which one.

The next revision was pushed from 2026 to 2027, so WPP 2024 is stable for now.
When WPP 2027 lands, this file gets a sibling (wpp2027.py) rather than an edit:
old vintages must keep resolving to the data they were actually built from.

The download URLs were read off the UN's own downloads page on 2026-08-07. They
are not published as a stable API, so if a fetch starts 404-ing, re-read the
links from https://population.un.org/wpp/downloads rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

REVISION = "WPP2024"
REVISION_LABEL = "UN World Population Prospects, 2024 revision"
SOURCE_PAGE = "https://population.un.org/wpp/downloads"
URLS_READ_ON = "2026-08-07"

_BASE = (
    "https://population.un.org/wpp/assets/Excel%20Files"
    "/1_Indicator%20(Standard)/CSV_FILES"
)


@dataclass(frozen=True)
class WppFile:
    """One downloadable file, and why the project wants it."""

    key: str
    filename: str
    purpose: str
    approx_mb: int
    required: bool = True

    @property
    def url(self) -> str:
        # The filenames contain spaces (e.g. "Zero migration"); percent-encode
        # only the space, because the UN's own links leave parentheses raw.
        return f"{_BASE}/{self.filename.replace(' ', '%20')}"


FILES: dict[str, WppFile] = {
    f.key: f
    for f in [
        WppFile(
            key="indicators_medium",
            filename="WPP2024_Demographic_Indicators_Medium.csv.gz",
            purpose=(
                "Location table (LocID, ISO3, type), sex ratio at birth, net "
                "migration totals, and the UN's own TFR/e0/births for checking."
            ),
            approx_mb=15,
        ),
        WppFile(
            key="indicators_variants",
            filename="WPP2024_Demographic_Indicators_OtherVariants.csv.gz",
            purpose=(
                "Same indicators for the non-medium variants. Total population "
                "under zero-migration and constant-fertility: the headline "
                "numbers the engine has to reproduce."
            ),
            approx_mb=30,
        ),
        WppFile(
            key="fertility_age1",
            filename="WPP2024_Fertility_by_Age1.csv.gz",
            purpose=(
                "Age-specific fertility rates by single year of age, 1950-2100. "
                "Covers ages 15-49 ONLY."
            ),
            approx_mb=287,
        ),
        WppFile(
            key="fertility_age5",
            filename="WPP2024_Fertility_by_Age5.csv.gz",
            purpose=(
                "The same rates in five-year groups, but covering ages 10-54. "
                "Needed because the single-age file omits mothers under 15 and "
                "over 49, who between them account for about 0.3% of world "
                "births - small, and enough to bias a 126-year projection."
            ),
            approx_mb=60,
        ),
        WppFile(
            key="pop_jan1_single_proj",
            filename=(
                "WPP2024_Population1JanuaryBySingleAgeSex_Medium_2024-2100.csv.gz"
            ),
            purpose=(
                "Base population at 1 January 2024 by single age and sex - the "
                "state vector the projection starts from (spec 5.1: fork at "
                "2024). Also the medium-variant reference path."
            ),
            approx_mb=64,
        ),
        WppFile(
            key="life_table_female",
            filename="WPP2024_Life_Table_Complete_Medium_Female_2024-2100.csv.gz",
            purpose="Complete (single-age) female life tables; Lx gives survival ratios.",
            approx_mb=193,
        ),
        WppFile(
            key="life_table_male",
            filename="WPP2024_Life_Table_Complete_Medium_Male_2024-2100.csv.gz",
            purpose="Complete (single-age) male life tables; Lx gives survival ratios.",
            approx_mb=194,
        ),
        WppFile(
            key="pop_jan1_age5_variants",
            filename="WPP2024_Population1JanuaryByAge5GroupSex_OtherVariants.csv.gz",
            purpose=(
                "Age structure under the non-medium variants, at 1 January so "
                "the time reference matches the engine exactly. The "
                "age-structure validation target."
            ),
            approx_mb=182,
        ),
        WppFile(
            key="pop_jan1_single_hist",
            filename=(
                "WPP2024_Population1JanuaryBySingleAgeSex_Medium_1950-2023.csv.gz"
            ),
            purpose="Historical population pyramids, 1950-2023. Needed for Phase 3, not Phase 2.",
            approx_mb=62,
            required=False,
        ),
    ]
}

REQUIRED_KEYS = [k for k, f in FILES.items() if f.required]

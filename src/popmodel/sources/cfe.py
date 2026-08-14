"""Pinned source inventory for completed-cohort parity distributions.

The Cohort Fertility and Education (CFE) Database publishes aggregate census,
register, and survey counts by birth cohort, sex, education, origin, and number
of children ever born.  The raw CSVs are free for research use but must not be
redistributed.  They therefore stay under ``data/raw``; this repository keeps
only their URLs, checksums, readers, and derived results.

One latest source is pinned per country.  This is deliberately a fixed list,
not a live scrape: a new census should cause a reviewed source update rather
than silently change the parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


SOURCE_PAGE = "https://www.eurrep.org/database/database/"
METHODS = (
    "https://www.eurrep.org/wp-content/uploads/"
    "CFE_Database_Methods_Protocol_2017-09-20.pdf"
)
TERMS = "https://www.eurrep.org/database/about/terms-of-use/"
DOWNLOAD_ROOT = "https://zozlak.org/eurrep"
ACCESSED = "2026-08-13"


@dataclass(frozen=True)
class Dataset:
    key: str
    country: str
    source: str
    observation_year: int | None

    @property
    def url(self) -> str:
        country = quote(self.country, safe="")
        source = quote(self.source, safe="")
        return f"{DOWNLOAD_ROOT}/{country}/{source}/raw"

    @property
    def filename(self) -> str:
        return f"{self.key}.csv"


def _d(key: str, country: str, source: str, year: int | None) -> Dataset:
    return Dataset(key, country, source, year)


# Latest source shown by the database on 2026-08-13.  France and Italy pool
# surveys from multiple years, so no single observation year is assigned and
# they are excluded from age-window analyses that need one.
DATASETS = {
    d.key: d
    for d in (
        _d("albania_2011", "Albania", "Census 2011", 2011),
        _d("argentina_2001", "Argentina", "Census 2001", 2001),
        _d("austria_2001", "Austria", "Census 2001", 2001),
        _d("belarus_2009", "Belarus", "Census 2009", 2009),
        _d("belgium_2001", "Belgium", "Census 2001", 2001),
        _d("bolivia_2001", "Bolivia", "Census 2001", 2001),
        _d(
            "bosnia_herzegovina_1991",
            "Bosnia-Herzegovina",
            "Census 1991",
            1991,
        ),
        _d("brazil_2010", "Brazil", "Census 2010", 2010),
        _d("bulgaria_2001", "Bulgaria", "Census 2001", 2001),
        _d("chile_2002", "Chile", "Census 2002", 2002),
        _d("colombia_2005", "Colombia", "Census 2005", 2005),
        _d("costa_rica_2011", "Costa Rica", "Census 2011", 2011),
        _d("croatia_2011", "Croatia", "Census 2011", 2011),
        _d("czech_republic_2001", "Czech Republic", "Census 2001", 2001),
        _d(
            "dominican_republic_2010",
            "Dominican Republic",
            "Census 2010",
            2010,
        ),
        _d("ecuador_2010", "Ecuador", "Census 2010", 2010),
        _d("el_salvador_2007", "El Salvador", "Census 2007", 2007),
        _d("estonia_2011", "Estonia", "Census 2011", 2011),
        _d("finland_2015", "Finland", "Population Register 2015", 2015),
        _d("france_surveys", "France", "Surveys 1982-2011", None),
        _d("germany_2012", "Germany", "Microcensus 2012", 2012),
        _d("greece_2011", "Greece", "Census 2011", 2011),
        _d("haiti_2003", "Haiti", "Census 2003", 2003),
        _d("hungary_2011", "Hungary", "Census 2011", 2011),
        _d("ireland_2011", "Ireland", "Census 2011", 2011),
        _d("italy_surveys", "Italy", "Surveys 2003-2009", None),
        _d("kosovo_2011", "Kosovo", "Census 2011", 2011),
        _d("macedonia_2002", "Macedonia", "Census 2002", 2002),
        _d("mexico_2010", "Mexico", "Census 2010", 2010),
        _d("montenegro_2011", "Montenegro", "Census 2011", 2011),
        _d("nicaragua_2005", "Nicaragua", "Census 2005", 2005),
        _d("panama_2010", "Panama", "Census 2010", 2010),
        _d("paraguay_2002", "Paraguay", "Census 2002", 2002),
        _d("peru_2007", "Peru", "Census 2007", 2007),
        _d("poland_2002", "Poland", "Fertility Survey 2002", 2002),
        _d("romania_2002", "Romania", "Census 2002", 2002),
        _d("russia_2010", "Russia", "Census 2010", 2010),
        _d("serbia_2011", "Serbia", "Census 2011", 2011),
        _d("slovakia_2011", "Slovakia", "Census 2011", 2011),
        _d("slovenia_2011", "Slovenia", "Census 2011", 2011),
        _d("south_korea_2010", "South Korea", "Census 2010", 2010),
        _d("spain_2011", "Spain", "Census 2011", 2011),
        _d("switzerland_2000", "Switzerland", "Census 2000", 2000),
        _d("uruguay_2011", "Uruguay", "Census 2011", 2011),
        _d("venezuela_2001", "Venezuela", "Census 2001", 2001),
    )
}

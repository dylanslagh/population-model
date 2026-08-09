"""When each country last actually counted its people.

Spec section 4.5 asks for a data-confidence layer rather than greying out
countries with thin data, on the grounds that "modelled from a 1932 census" is
more honest and more interesting than a blank polygon. There are no gaps in
WPP - every country has a full set of numbers - but the numbers rest on very
different amounts of evidence, and nothing on the map says so.

The source
----------
The UN Statistics Division maintains the census dates of every country across
the 1990, 2000, 2010, 2020 and 2030 rounds. It is the same institution that
produces WPP, published as a plain HTML page.

    https://unstats.un.org/unsd/demographic-social/census/censusdates/

What this measures, and what it does not
----------------------------------------
It measures ONE thing: how long since a country ran a population census. That
is a real and checkable number, and it is the single best available proxy for
how much of a country's demography is observed rather than modelled.

It is NOT a composite data-quality score, and it must never be presented as
one. Two honest caveats travel with it:

* **A country with no census can still have excellent data.** Denmark, Sweden,
  Finland and the Netherlands run register-based censuses - continuous
  administrative counting rather than a door-to-door enumeration - and their
  demography is among the best measured on earth. The UNSD table gives them
  dates, so they score well here, but the reason is not the one the number
  implies.
* **A recent census can still be poor.** Coverage, completeness and political
  interference are not visible in a date.

Spec section 4.5 also asks for DHS coverage and vital-registration
completeness. Those are not here. One dimension, sourced and labelled, is
worth more than three where two were invented.
"""

from __future__ import annotations

URL = "https://unstats.un.org/unsd/demographic-social/census/censusdates/"
SOURCE = "UN Statistics Division, census dates by country"
FETCHED_NOTE = "HTML page; the layout is parsed in ingest/census.py"

# The rounds the page carries, oldest first. A date in parentheses is a
# PLANNED census, not one that happened, and is ignored.
ROUNDS = ["1990", "2000", "2010", "2020", "2030"]

# UNSD spells some countries differently from WPP. Both are UN DESA, so most
# names agree exactly; these are the ones that do not. Keyed by the UNSD name,
# valued with the WPP name. Anything not covered here and not matched by
# normalisation is a build error - see ingest/census.py.
NAME_OVERRIDES = {
    "Korea, Democratic People's Republic of": "Dem. People's Republic of Korea",
    "Korea, Republic of": "Republic of Korea",
    "Palestine, State of": "State of Palestine",
    "Iran, Islamic Republic of": "Iran (Islamic Republic of)",
    "Bolivia, Plurinational State of": "Bolivia (Plurinational State of)",
    "Venezuela, Bolivarian Republic of": "Venezuela (Bolivarian Republic of)",
    "Micronesia, Federated States of": "Micronesia (Fed. States of)",
    "Tanzania, United Republic of": "United Republic of Tanzania",
    "Moldova, Republic of": "Republic of Moldova",
    "Macedonia, The former Yugoslav Republic of": "North Macedonia",
    "Hong Kong Special Administrative Region of China": "China, Hong Kong SAR",
    "Macao Special Administrative Region of China": "China, Macao SAR",
    "Netherlands (Kingdom of the)": "Netherlands",
    "Turkey": "Türkiye",
    "Czech Republic": "Czechia",
    "Cape Verde": "Cabo Verde",
    "Swaziland": "Eswatini",
    "Burma": "Myanmar",
    "Vatican City": "Holy See",
    "Holy See (Vatican City State)": "Holy See",
    "Falkland Islands (Malvinas)": "Falkland Islands (Malvinas)",
    "China, Hong Kong SAR": "China, Hong Kong SAR",
    "China, Macao SAR": "China, Macao SAR",
    "Wallis and Futuna Islands": "Wallis and Futuna Islands",
    "Saint Helena ex. dep.": "Saint Helena",
    "Sint Maarten (Dutch part)": "Sint Maarten (Dutch part)",
    "Curacao": "Curaçao",
    "Reunion": "Réunion",
    "Cote d'Ivoire": "Côte d'Ivoire",
    "Saint Barthelemy": "Saint Barthélemy",
    "Congo, Democratic Republic of the": "Democratic Republic of the Congo",
    "Libya Arab Jamahiriya": "Libya",
    "Bolivia": "Bolivia (Plurinational State of)",
    "Venezuela": "Venezuela (Bolivarian Republic of)",
    "Sint Maarten": "Sint Maarten (Dutch part)",
    "Saint-Martin": "Saint Martin (French part)",
    "Saint-Barthelemy": "Saint Barthélemy",
    "Sao Tome and Principe": "Sao Tome and Principe",
}

# WPP countries UNSD does not list at all, with the reason. These get a
# "not listed" confidence rather than being dropped or silently scored.
NOT_LISTED = {
    "Kosovo (under UNSC res. 1244)":
        "not a UN member, so UNSD does not carry it in the census-round table",
    "China, Taiwan Province of China":
        "not listed by UNSD, which carries China, Hong Kong SAR and Macao SAR "
        "but no Taiwan row. Taiwan does run a census; the omission is political, "
        "not evidential, and scoring it as unmeasured would be wrong",
}

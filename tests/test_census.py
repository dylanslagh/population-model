"""Tests for the census-date parser.

Every case here is a shape the real UNSD page actually contains, and each one
was found by a wrong answer rather than by imagination:

* Continuation rows nearly shipped a map saying the United Kingdom had not run
  a census since 1985, and put Finland at 1995 and Malta at 2005.
* Section headings live inside the first country's own cells, which silently
  deleted Afghanistan and every other continent's first country.
* Parenthesised dates are censuses that have not happened yet.
"""

from __future__ import annotations

import pandas as pd
import pytest

from popmodel.ingest import census


def row(name, *dates):
    cells = "".join(f'<div class="col-md-2" align="right"> {d} </div>' for d in dates)
    return f'<div class="row"><div class="col-md-2"> {name} </div>{cells}</div></div>'


def page(*rows):
    return "<html>" + "".join(rows) + "</html>"


SMALL = dict(min_rows=1, min_records=1)


def parse_one(*rows):
    return census.parse(page(*rows), **SMALL)[0]


def test_a_plain_row_takes_the_latest_real_year():
    r = parse_one(row("Zambia", "20 August 1990", "25 October 2000", "16 Oct.-5 Nov. 2010",
                      "18 August 2022", "(18 August 2030)"))
    assert r.unsd_name == "Zambia"
    assert r.last_census_year == 2022


def test_a_planned_census_in_parentheses_does_not_count():
    r = parse_one(row("Nowhere", "1 January 1990", "-", "-", "-", "(2031)"))
    assert r.last_census_year == 1990


def test_a_country_with_no_census_at_all_is_none_not_zero():
    r = parse_one(row("Lebanon", "-", "-", "-", "-", "(...)"))
    assert r.last_census_year is None


def test_footnote_markers_are_stripped_from_the_name():
    r = parse_one(row("Denmark <sup>(3)</sup>", "1 January 1991", "-", "-", "-", "-"))
    assert r.unsd_name == "Denmark"


def test_a_section_heading_inside_the_first_cell_does_not_eat_the_country():
    """Afghanistan shares its row with the ASIA heading on the real page."""
    name = '<div class="headline"><h5><strong>ASIA</strong><br>Countries or areas</h5></div> Afghanistan'
    first_date = '<div class="headline"><h5>1990 round<br>(1985-1994)</h5></div> 1 January 1990'
    html = ('<div class="row">'
            f'<div class="col-md-2"> {name} </div>'
            f'<div class="col-md-2" align="right"> {first_date} </div>'
            '<div class="col-md-2" align="right"> - </div>'
            '<div class="col-md-2" align="right"> - </div>'
            '<div class="col-md-2" align="right"> - </div>'
            '</div></div>')
    recs = census.parse(page(html), **SMALL)
    assert recs[0].unsd_name == "Afghanistan"
    # And the round label's own year range must not be read as a census.
    assert recs[0].last_census_year == 1990


def test_a_blank_named_row_continues_the_country_above_it():
    """Finland's later censuses are on a second row with no name."""
    recs = census.parse(page(
        row("Finland <sup>(3)</sup>", "17 November 1985", "31 December 1995", "", "", "(2031)"),
        row("", "31 December 1990", "31 December 2000", "31 December 2010", "1 January 2021"),
    ), **SMALL)
    assert recs[0].unsd_name == "Finland"
    assert recs[0].last_census_year == 2021


def test_a_dashed_row_continues_the_country_above_it():
    """The UK's own row is empty; its censuses are under its constituent countries."""
    recs = census.parse(page(
        row("United Kingdom", "", "", "", ""),
        row("- England and Wales", "21 April 1991", "29 April 2001", "27 March 2011", "21 March 2021"),
        row("- Scotland", "21 April 1991", "29 April 2001", "27 March 2011", "20 March 2022"),
    ), **SMALL)
    assert recs[0].unsd_name == "United Kingdom"
    assert recs[0].last_census_year == 2022
    assert len(recs) == 1  # the two continuations did not become countries


def test_html_entities_are_decoded():
    r = parse_one(row("C&ocirc;te d'Ivoire", "1 March 1988", "-", "-", "-", "-"))
    assert r.unsd_name == "Côte d'Ivoire"


def test_normalising_uninverts_and_expands_saint():
    assert census._normalise("Palestine, State of") == census._normalise("State of Palestine")
    assert census._normalise("St. Lucia") == census._normalise("Saint Lucia")
    assert census._normalise("Curaçao") == census._normalise("Curacao")


def test_bands_are_measured_from_the_base_year():
    assert census._band(2021) == "within 5 years"
    assert census._band(2011) == "5 to 14 years"
    assert census._band(2006) == "15 years or more"
    assert census._band(None) == "none since 1985"


def test_an_unaccounted_country_raises_rather_than_being_dropped():
    countries = pd.DataFrame([(4, "AFG", "Atlantis")],
                             columns=["LocID", "ISO3_code", "Location"])
    with pytest.raises(census.CensusParseError, match="no census record and no recorded reason"):
        census.match_to_wpp([], countries)


def test_a_page_that_changed_shape_raises_instead_of_returning_a_short_list():
    with pytest.raises(census.CensusParseError, match="layout has changed"):
        census.parse("<html>nothing here</html>")

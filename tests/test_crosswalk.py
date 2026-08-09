"""Tests for the country-to-map join.

The behaviour worth protecting is the refusal. It is easy to write a join that
quietly drops the countries it cannot match, and the result looks fine - a map
with 228 shapes on it looks exactly like a map with 237 shapes on it unless you
count. Spec rule 5 exists because of that.
"""

from __future__ import annotations

import pandas as pd
import pytest

from popmodel import crosswalk


def countries(rows):
    return pd.DataFrame(rows, columns=["LocID", "ISO3_code", "Location"])


def test_an_unaccounted_country_raises(monkeypatch):
    monkeypatch.setattr(crosswalk, "_load", lambda key: [])
    with pytest.raises(crosswalk.CrosswalkError, match="no shape and no recorded exception"):
        crosswalk.build(countries([(999, "ZZZ", "Atlantis")]))


def test_the_error_names_the_country_so_it_can_be_fixed(monkeypatch):
    monkeypatch.setattr(crosswalk, "_load", lambda key: [])
    with pytest.raises(crosswalk.CrosswalkError) as exc:
        crosswalk.build(countries([(999, "ZZZ", "Atlantis")]))
    assert "Atlantis" in str(exc.value) and "999" in str(exc.value)


def test_a_shape_with_no_population_and_no_reason_raises(monkeypatch):
    feature = {"properties": {"UN_A3": "999", "ADMIN": "Nowhere", "ISO_A3": "NOW"},
               "geometry": {"type": "Polygon", "coordinates": []}}
    monkeypatch.setattr(crosswalk, "_load", lambda key: [feature] if key == "countries" else [])
    with pytest.raises(crosswalk.CrosswalkError, match="no recorded reason"):
        crosswalk.build(countries([]))


def test_multiple_shapes_for_one_country_are_merged_not_discarded():
    poly_a = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    poly_b = {"type": "Polygon", "coordinates": [[[5, 5], [6, 5], [6, 6], [5, 5]]]}
    merged = crosswalk._merge([{"geometry": poly_a}, {"geometry": poly_b}])
    assert merged["type"] == "MultiPolygon"
    assert len(merged["coordinates"]) == 2


def test_merging_flattens_an_existing_multipolygon():
    multi = {"type": "MultiPolygon", "coordinates": [[[[0, 0]]], [[[1, 1]]]]}
    single = {"type": "Polygon", "coordinates": [[[2, 2]]]}
    merged = crosswalk._merge([{"geometry": multi}, {"geometry": single}])
    assert len(merged["coordinates"]) == 3


def test_un_code_prefers_the_un_field_then_falls_back():
    assert crosswalk._un_code({"UN_A3": "716"}) == 716
    assert crosswalk._un_code({"UN_A3": "-099", "ISO_N3_EH": "412"}) == 412
    assert crosswalk._un_code({"UN_A3": "-099", "ISO_N3": "-99"}) is None
    assert crosswalk._un_code({}) is None


def test_a_name_override_that_no_longer_matches_raises(monkeypatch):
    """If Natural Earth renames Kosovo, that must break loudly, not drop it."""
    monkeypatch.setattr(crosswalk, "_load", lambda key: [])
    with pytest.raises(crosswalk.CrosswalkError, match="no longer present"):
        crosswalk.build(countries([(412, "XKX", "Kosovo (under UNSC res. 1244)")]))


def test_every_exception_carries_a_written_reason():
    """No entry may be added to the exception lists without saying why."""
    for reason in crosswalk.SUPPLEMENT_FROM_MAP_UNITS.values():
        assert len(reason) > 20 and "-" in reason
    for _, why in crosswalk.NAME_OVERRIDES.values():
        assert len(why) > 20
    for entry in crosswalk.POINT_ONLY.values():
        assert len(entry[3]) > 15
    for reason in crosswalk.NO_POPULATION.values():
        assert len(reason) > 20

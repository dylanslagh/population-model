"""The public site may not disagree with the results it is built from."""

from __future__ import annotations

import base64
import importlib.util
import json
from array import array
from pathlib import Path

import pytest

from popmodel import paths

SCRIPT = paths.REPO_ROOT / "scripts" / "build_site.py"
SPEC = importlib.util.spec_from_file_location("build_site", SCRIPT)
assert SPEC and SPEC.loader
build_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_site)

SITE = paths.REPO_ROOT / "site"
STORY = json.loads((SITE / "data" / "story.json").read_text(encoding="utf-8"))
BODY = (SITE / "body.html").read_text(encoding="utf-8")


def test_every_number_printed_on_the_page_matches_the_results():
    """The guard that keeps the prose from drifting away from the model."""

    checked = build_site.check_numbers(BODY, STORY)
    assert checked > 30


def test_a_stale_number_on_the_page_fails_the_build():
    page = '<p><b class="v" data-v="boundary.rate" data-dp="2">9.99%</b></p>'
    with pytest.raises(build_site.BuildError, match="page says 9.99%"):
        build_site.check_numbers(page, STORY)


def test_a_stale_phrase_on_the_page_fails_the_build():
    page = '<p><span class="v" data-v="paper.version">1.0.0</span></p>'
    with pytest.raises(build_site.BuildError, match="results say"):
        build_site.check_numbers(page, STORY)


def test_a_path_that_does_not_exist_fails_the_build():
    page = '<p><span class="v" data-v="boundary.invented">1</span></p>'
    with pytest.raises(build_site.BuildError, match="does not exist"):
        build_site.check_numbers(page, STORY)


def test_paths_may_index_into_a_list():
    assert build_site.resolve(STORY, "ladder.0.value") == STORY["ladder"][0]["value"]


def test_the_page_rounds_rather_than_restates():
    """8.78 may be printed as 8.8, but not as 8.9."""

    assert build_site.check_numbers(
        '<b class="v" data-v="horizon.unEquivalent2150">8.8</b>', STORY
    ) == 1
    with pytest.raises(build_site.BuildError):
        build_site.check_numbers(
            '<b class="v" data-v="horizon.unEquivalent2150">8.9</b>', STORY
        )


# ------------------------------------------------------------------- globe --

GLOBE = json.loads((SITE / "data" / "globe.json").read_text(encoding="utf-8"))


def decode(key: str, typecode: str):
    buffer = array(typecode)
    buffer.frombytes(base64.b64decode(GLOBE[key]))
    return buffer


def test_the_globe_carries_every_country():
    """Standing instruction 5: never drop a country silently."""

    assert len(GLOBE["iso"]) == 237
    assert len(GLOBE["names"]) == 237
    assert len(set(GLOBE["iso"])) == 237


def test_every_country_has_lights_enough_for_its_own_peak():
    offsets = decode("lightOffsets", "I")
    population = decode("population", "H")
    years = GLOBE["lastYear"] - GLOBE["firstYear"] + 1
    assert len(population) == 237 * years
    for index, iso in enumerate(GLOBE["iso"]):
        pool = offsets[index + 1] - offsets[index]
        peak = max(population[index * years:(index + 1) * years])
        needed = peak * GLOBE["populationUnit"] / GLOBE["peoplePerLight"]
        assert pool >= needed, f"{iso} has {pool} lights for {needed:.0f}"


def test_the_lights_sit_on_the_planet():
    lights = decode("lights", "h")
    assert len(lights) == 2 * decode("lightOffsets", "I")[-1]
    for value in lights[::2]:
        assert -18000 <= value <= 18000
    for value in lights[1::2]:
        assert -9000 <= value <= 9000


def test_the_world_series_is_the_sum_of_its_countries():
    population = decode("population", "H")
    years = GLOBE["lastYear"] - GLOBE["firstYear"] + 1
    for year_index in (0, years // 2, years - 1):
        total = sum(
            population[country * years + year_index] for country in range(237)
        ) * GLOBE["populationUnit"]
        assert GLOBE["world"][year_index] == pytest.approx(total / 1e9, abs=0.02)


def test_the_globe_stops_where_the_un_stops():
    """Nothing on the globe is this project extrapolating past 2100."""

    assert GLOBE["lastYear"] == 2100
    assert GLOBE["estimatesTo"] == 2023

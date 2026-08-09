"""Join the UN's 237 countries to shapes on a map, and account for every one.

Spec section 4.4 says this is where the data is actually messy, and section 14
rule 5 says an unmatched code is a build error and never a silent drop. Both are
enforced here: `build()` raises unless all 237 WPP countries are accounted for,
either by a matched shape or by an exception that a human wrote down and
justified.

The scale of the problem, once the right key is used
----------------------------------------------------
Natural Earth carries the UN's own M49 numeric code, and WPP's LocID for a
country is that code. Joining on it matches 228 of 237 immediately. Every
remaining case below is a real disagreement about what a country is, not a
data-cleaning annoyance, so each is named and decided individually.

The nine, and what was decided
------------------------------
* **Mayotte, Réunion, Guadeloupe, Martinique, French Guiana.** French overseas
  departments. Legally France, and drawn as France on an ordinary world map,
  but the UN counts their populations separately and so does WPP. Natural
  Earth's finer `map_units` layer separates them, so they get their own shapes
  from there. Spec 4.4 called these out by name.
* **Bonaire, Sint Eustatius and Saba.** The Caribbean Netherlands, same
  situation, same fix.
* **Tokelau.** New Zealand territory, ~1,500 people, folded into New Zealand in
  the base layer and separate in map_units.
* **Kosovo.** Declared independence in 2008 and is not a UN member, so it has
  no M49 code at all: Natural Earth records `-099`. The UN nevertheless
  publishes population for it under LocID 412, labelled "Kosovo (under UNSC
  res. 1244)". Matched by name, deliberately and visibly, because there is no
  key to match on.
* **Gibraltar.** Six square kilometres. Below the resolution of the 50m data
  entirely. It gets no polygon and is flagged `point_only`, so the map can draw
  a marker rather than pretend it has an outline or drop 39,000 people.

Two other things the join has to handle
---------------------------------------
Several countries appear as more than one shape - Australia plus its offshore
islands, Portugal plus Madeira and the Azores - which get merged into one
multi-part shape rather than one being picked and the rest quietly discarded.

And eight Natural Earth shapes have no WPP country: Antarctica, the British
Indian Ocean Territory, South Georgia, the French Southern Territories, Heard
Island, Pitcairn, Norfolk Island and Åland. The first six are uninhabited or
nearly so and the UN does not project them; Åland is counted inside Finland and
Norfolk Island inside Australia. They are recorded as `no_population` so the map
can grey them honestly instead of leaving a hole.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from popmodel import paths
from popmodel.sources import fetch, naturalearth

# WPP LocID -> the reason it cannot be matched on the UN numeric code, and what
# to do instead. Nothing may be added here without a sentence saying why.
SUPPLEMENT_FROM_MAP_UNITS = {
    175: "Mayotte - French overseas department, drawn inside France in the base layer",
    254: "French Guiana - French overseas department",
    312: "Guadeloupe - French overseas department",
    474: "Martinique - French overseas department",
    535: "Bonaire, Sint Eustatius and Saba - Caribbean Netherlands",
    638: "Reunion - French overseas department",
    772: "Tokelau - New Zealand territory, folded into New Zealand in the base layer",
}

# Matched by name because the entity has no UN numeric code to match on.
NAME_OVERRIDES = {
    412: ("Kosovo", "not a UN member, so Natural Earth records no M49 code"),
}

# Real places with real populations and no shape at this resolution.
POINT_ONLY = {
    292: ("Gibraltar", 36.14, -5.35, "6.8 sq km, below the resolution of the 50m data"),
}

# Natural Earth shapes with no WPP population, and why.
NO_POPULATION = {
    10: "Antarctica - no permanent population",
    86: "British Indian Ocean Territory - military base only, not projected",
    239: "South Georgia and the South Sandwich Islands - no permanent population",
    248: "Aland - counted inside Finland by the UN",
    260: "French Southern and Antarctic Lands - no permanent population",
    334: "Heard Island and McDonald Islands - no permanent population",
    574: "Norfolk Island - counted inside Australia by the UN",
    612: "Pitcairn Islands - about 50 people, not separately projected",
}


class CrosswalkError(RuntimeError):
    """A country could not be accounted for. Spec rule 5: never drop silently."""


@dataclass
class Crosswalk:
    table: pd.DataFrame  # one row per WPP country
    shapes: dict[int, dict] = field(default_factory=dict)  # loc_id -> GeoJSON geometry
    unmatched_shapes: list[dict] = field(default_factory=list)

    @property
    def n_with_shape(self) -> int:
        return int(self.table.has_shape.sum())

    def geometry(self, loc_id: int) -> dict | None:
        return self.shapes.get(int(loc_id))


def _load(key: str) -> list[dict]:
    with Path(fetch.geo_path(key)).open(encoding="utf-8") as fh:
        return json.load(fh)["features"]


def _un_code(props: dict) -> int | None:
    for field_name in naturalearth.CODE_FIELDS:
        raw = str(props.get(field_name) or "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
    return None


def _index_by_code(features: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for f in features:
        code = _un_code(f["properties"])
        if code is not None:
            out.setdefault(code, []).append(f)
    return out


def _merge(features: list[dict]) -> dict:
    """One shape per country. Several shapes become one multi-part shape.

    Australia is Australia plus Ashmore and Cartier; Portugal is the mainland
    plus Madeira plus the Azores. Keeping the largest and dropping the rest
    would silently delete real land.
    """
    if len(features) == 1:
        return features[0]["geometry"]
    parts: list = []
    for f in features:
        g = f["geometry"]
        if g["type"] == "Polygon":
            parts.append(g["coordinates"])
        elif g["type"] == "MultiPolygon":
            parts.extend(g["coordinates"])
        else:
            raise CrosswalkError(f"unexpected geometry type {g['type']}")
    return {"type": "MultiPolygon", "coordinates": parts}


def build(countries: pd.DataFrame) -> Crosswalk:
    """Match every WPP country to a shape, or to a written-down reason.

    `countries` is the frame from ingest.wpp.country_table(): LocID, ISO3_code,
    Location.
    """
    base = _index_by_code(_load("countries"))
    units = _index_by_code(_load("map_units"))
    units_by_name = {
        (f["properties"].get("NAME") or "").strip(): f for f in _load("map_units")
    }

    rows = []
    shapes: dict[int, dict] = {}
    for _, c in countries.iterrows():
        loc = int(c["LocID"])
        name = c["Location"]
        iso = c["ISO3_code"]

        if loc in base:
            shapes[loc] = _merge(base[loc])
            rows.append((loc, iso, name, True, "matched", "UN M49 code, base layer",
                         len(base[loc]), None, None))
        elif loc in SUPPLEMENT_FROM_MAP_UNITS and loc in units:
            shapes[loc] = _merge(units[loc])
            rows.append((loc, iso, name, True, "matched", SUPPLEMENT_FROM_MAP_UNITS[loc],
                         len(units[loc]), None, None))
        elif loc in NAME_OVERRIDES:
            ne_name, why = NAME_OVERRIDES[loc]
            feature = units_by_name.get(ne_name)
            if feature is None:
                raise CrosswalkError(
                    f"{name} (LocID {loc}) is matched by the name {ne_name!r}, which "
                    "is no longer present in Natural Earth. The override needs "
                    "revisiting; do not drop the country."
                )
            shapes[loc] = feature["geometry"]
            rows.append((loc, iso, name, True, "matched_by_name", why, 1, None, None))
        elif loc in POINT_ONLY:
            _, lat, lon, why = POINT_ONLY[loc]
            rows.append((loc, iso, name, False, "point_only", why, 0, lat, lon))
        else:
            raise CrosswalkError(
                f"{name} (ISO {iso}, LocID {loc}) has no shape and no recorded "
                "exception.\n"
                "Spec rule 5: this is a build error, not something to drop. Decide "
                "what the right answer is and write it into crosswalk.py with a "
                "reason, the way the other nine are."
            )

    table = pd.DataFrame(
        rows,
        columns=["loc_id", "iso3", "name", "has_shape", "match", "reason",
                 "n_shapes", "point_lat", "point_lon"],
    ).sort_values("loc_id").reset_index(drop=True)

    known = set(countries["LocID"].astype(int))
    leftovers = []
    for code, feats in base.items():
        if code in known:
            continue
        props = feats[0]["properties"]
        leftovers.append({
            "un_code": code,
            "name": props.get("ADMIN") or props.get("NAME"),
            "iso_a3": props.get("ISO_A3"),
            "reason": NO_POPULATION.get(code, "NOT ACCOUNTED FOR"),
        })
    unexplained = [x for x in leftovers if x["reason"] == "NOT ACCOUNTED FOR"]
    if unexplained:
        raise CrosswalkError(
            "Natural Earth shapes with no WPP country and no recorded reason:\n"
            + "\n".join(f"  {x['un_code']} {x['name']}" for x in unexplained)
            + "\nAdd them to NO_POPULATION with a reason, or work out what was missed."
        )

    return Crosswalk(table=table, shapes=shapes, unmatched_shapes=leftovers)


def table_path() -> Path:
    return paths.REFERENCE / "crosswalk.csv"


def save(cw: Crosswalk) -> Path:
    """Write the crosswalk table. It is committed, so a reviewer can read it."""
    p = table_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cw.table.to_csv(p, index=False)
    (p.parent / "crosswalk_no_population.csv").write_text(
        pd.DataFrame(cw.unmatched_shapes).to_csv(index=False), encoding="utf-8"
    )
    return p


def load() -> pd.DataFrame:
    p = table_path()
    if not p.exists():
        raise FileNotFoundError(f"{p} missing. Run: python scripts/build_crosswalk.py")
    return pd.read_csv(p)

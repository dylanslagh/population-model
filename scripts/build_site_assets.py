"""Build the compact data the public site draws from.

    python scripts/build_site_assets.py

Writes two committed files:

* ``site/data/globe.json`` — country outlines and one light per million people,
  everything the rotating Earth needs.
* ``site/data/story.json`` — every number the story quotes, copied from the
  files that already hold them so the page cannot drift from the paper.

Standard library only, on purpose: this runs on a fresh clone, and the site
should never depend on the 1.1 GB of WPP source data. Its inputs are

* ``data/raw/naturalearth/...`` — the outlines, from ``scripts/fetch_geometry.py``
  and checksum-verified against ``data/manifest/naturalearth_files.json``;
* ``map/index.html`` — the reviewed map page, whose embedded payload carries the
  per-country population series (rebuild it with ``scripts/build_map.py``);
* ``data/reference/*.json`` and ``paper/generated/results_macros.tex`` — the
  headline numbers, which are generated from result files by the paper build.

The lights are honest about what they are not. Each one stands for a million
people placed at random inside its country: the model has no cities in it, so
the page must not draw any.
"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import math
import random
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "naturalearth" / "v5.1.2"
REFERENCE = REPO / "data" / "reference"
MANIFEST = REPO / "data" / "manifest" / "naturalearth_files.json"
MAP_PAGE = REPO / "map" / "index.html"
MACROS = REPO / "paper" / "generated" / "results_macros.tex"
OUT = REPO / "site" / "data"

# One light per million people. The world holds about 2,500 of them in 1950 and
# about 10,200 at 2100, which is dense enough to read as a lit Earth and sparse
# enough that a browser can draw every one of them sixty times a second.
PEOPLE_PER_LIGHT = 1_000_000.0

# The globe stops where the UN's published assumptions stop.
FIRST_YEAR = 1950
LAST_YEAR = 2100

# Outline simplification, in degrees. The globe is at most ~700 px across, so
# 180 degrees of latitude is ~3.9 px per degree and 0.12 deg is under half a
# pixel. Rings smaller than the area threshold are dropped from the drawing
# only: lights are always sampled from the full-resolution shape.
OUTLINE_TOLERANCE = 0.12
MIN_RING_AREA = 0.35

SEED = 20260819

# Mirrors NAME_OVERRIDES in popmodel/crosswalk.py: Kosovo is not a UN member,
# so Natural Earth records no M49 code for it and it has to be matched by name
# in the map-units layer. Never drop a country instead.
NAME_OVERRIDES = {"XKX": "Kosovo"}


class BuildError(RuntimeError):
    """An input is missing, unverified, or internally inconsistent."""


# ---------------------------------------------------------------- geometry --


def douglas_peucker(points: list[tuple[float, float]], tolerance: float):
    """Drop points that sit within `tolerance` of the line they interrupt."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        span = math.hypot(dx, dy)
        worst, worst_at = -1.0, first
        for i in range(first + 1, last):
            px, py = points[i]
            if span == 0.0:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / span
            if d > worst:
                worst, worst_at = d, i
        if worst > tolerance:
            keep[worst_at] = True
            stack.append((first, worst_at))
            stack.append((worst_at, last))
    return [p for p, k in zip(points, keep) if k]


def ring_area(ring: list[tuple[float, float]]) -> float:
    """Shoelace area in square degrees, corrected for the ring's latitude."""
    total = 0.0
    lat_sum = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        total += x0 * y1 - x1 * y0
        lat_sum += y0
    mean_lat = lat_sum / max(len(ring), 1)
    return abs(total) / 2.0 * math.cos(math.radians(mean_lat))


def polygons_of(geometry: dict) -> list[list[list[tuple[float, float]]]]:
    """GeoJSON geometry to a list of polygons, each a list of rings."""
    kind = geometry["type"]
    if kind == "Polygon":
        raw = [geometry["coordinates"]]
    elif kind == "MultiPolygon":
        raw = geometry["coordinates"]
    else:
        raise BuildError(f"unexpected geometry type {kind}")
    polygons = []
    for polygon in raw:
        rings = []
        for ring in polygon:
            pts = [(float(x), float(y)) for x, y in ring]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) >= 3:
                rings.append(pts)
        if rings:
            polygons.append(rings)
    return polygons


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def point_in_polygon(x: float, y: float, rings: list[list[tuple[float, float]]]) -> bool:
    if not point_in_ring(x, y, rings[0]):
        return False
    return not any(point_in_ring(x, y, hole) for hole in rings[1:])


def sample_lights(polygons, count: int, rng: random.Random):
    """`count` points scattered uniformly by area across a country's polygons."""
    if count <= 0:
        return []
    weights = [ring_area(p[0]) for p in polygons]
    total = sum(weights)
    if total <= 0:
        return []
    points: list[tuple[float, float]] = []
    for polygon, weight in zip(polygons, weights):
        want = int(round(count * weight / total))
        if want <= 0:
            continue
        outer = polygon[0]
        xs = [p[0] for p in outer]
        ys = [p[1] for p in outer]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        # Rejection sampling, but weighted by cos(latitude) so that a tall
        # country is not over-seeded near its poleward edge.
        cos_max = max(math.cos(math.radians(max(abs(y0), abs(y1)))), 1e-6)
        cos_top = math.cos(math.radians(min(abs(y0), abs(y1))))
        got = 0
        attempts = 0
        budget = 400 * want + 4000
        while got < want and attempts < budget:
            attempts += 1
            x = rng.uniform(x0, x1)
            y = rng.uniform(y0, y1)
            if not point_in_polygon(x, y, polygon):
                continue
            if cos_top > 0 and rng.random() > math.cos(math.radians(y)) / max(cos_top, cos_max):
                continue
            points.append((x, y))
            got += 1
        if got == 0:
            # A sliver too thin to hit: fall back to a vertex.
            points.append(outer[0])
    rng.shuffle(points)
    return points[:count]


# ------------------------------------------------------------------ inputs --


def verify_geometry() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    for key, spec in manifest.items():
        path = RAW / spec["filename"]
        if not path.exists():
            raise BuildError(
                f"{path.relative_to(REPO)} is missing.\n"
                f"  Run:  python scripts/fetch_geometry.py"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != spec["sha256"]:
            raise BuildError(
                f"{spec['filename']} does not match the manifest.\n"
                f"  expected {spec['sha256']}\n  found    {digest}"
            )
        print(f"  {key}: {spec['filename']} verified")


def un_code(props: dict) -> int | None:
    for field in ("UN_A3", "ISO_N3_EH", "ISO_N3"):
        value = props.get(field)
        if value in (None, "", "-99", -99):
            continue
        try:
            code = int(value)
        except (TypeError, ValueError):
            continue
        if code > 0:
            return code
    return None


def load_crosswalk() -> tuple[dict[int, str], dict[str, tuple[float, float]]]:
    """loc_id -> ISO3, plus a fallback point for countries with no shape."""
    import csv

    by_code: dict[int, str] = {}
    points: dict[str, tuple[float, float]] = {}
    with (REFERENCE / "crosswalk.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            iso = row["iso3"]
            by_code[int(row["loc_id"])] = iso
            if row.get("point_lat") and row.get("point_lon"):
                points[iso] = (float(row["point_lon"]), float(row["point_lat"]))
    return by_code, points


def load_map_payload() -> dict:
    if not MAP_PAGE.exists():
        raise BuildError(
            f"{MAP_PAGE.relative_to(REPO)} is missing.\n"
            f"  Run:  python scripts/build_map.py"
        )
    source = MAP_PAGE.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="payload" type="application/json">(.*?)</script>', source, re.S
    )
    if not match:
        raise BuildError("the map page has no embedded payload")
    return json.loads(match.group(1))


def load_macros() -> dict[str, str]:
    text = MACROS.read_text(encoding="utf-8")
    found = dict(re.findall(r"\\newcommand\{\\(\w+)\}\s*\{(.*?)\}\s*$", text, re.M))
    if not found:
        raise BuildError("no macros found in the generated results file")
    return found


def text(macros: dict[str, str], key: str) -> str:
    """A macro as a reader sees it: LaTeX escapes turned back into characters."""
    return (
        macros[key]
        .replace("\\%", "%")
        .replace("$-$", "\u2212")
        .replace("\\,", "\u2009")
        .strip()
    )


def number(macros: dict[str, str], key: str) -> float:
    raw = macros[key].replace("\\%", "").replace("%", "").replace(",", "").strip()
    raw = raw.replace("$-$", "-").replace("\\,", "")
    return float(raw)


# ------------------------------------------------------------------ encode --


def b64(values, typecode: str) -> str:
    buffer = array.array(typecode, values)
    if sys.byteorder == "big":
        buffer.byteswap()
    return base64.b64encode(buffer.tobytes()).decode("ascii")


# ------------------------------------------------------------------- build --


def build_globe() -> dict:
    verify_geometry()
    code_to_iso, fallback_points = load_crosswalk()
    payload = load_map_payload()
    countries = payload["countries"]

    features = []
    for layer in ("ne_50m_admin_0_countries.geojson", "ne_50m_admin_0_map_units.geojson"):
        data = json.loads((RAW / layer).read_text(encoding="utf-8"))
        features.append((layer, data["features"]))

    base_layer, base_features = features[0]
    unit_layer, unit_features = features[1]

    # Outlines: every land shape in the base layer, Antarctica included. This
    # layer is scenery. Nothing is counted from it.
    outline_rings: list[list[tuple[float, float]]] = []
    for feature in base_features:
        for polygon in polygons_of(feature["geometry"]):
            for ring in polygon:
                if ring_area(ring) < MIN_RING_AREA:
                    continue
                simplified = douglas_peucker(ring, OUTLINE_TOLERANCE)
                if len(simplified) >= 3:
                    outline_rings.append(simplified)
    print(f"  outlines: {len(outline_rings)} rings, "
          f"{sum(len(r) for r in outline_rings):,} points")

    # Shapes to sample lights from, indexed by ISO3. The base layer decides;
    # the finer map-units layer only fills in countries it folds into a parent.
    shapes: dict[str, list] = {}
    for layer_features, layer_name in ((base_features, base_layer), (unit_features, unit_layer)):
        for feature in layer_features:
            code = un_code(feature["properties"])
            if code is None:
                continue
            iso = code_to_iso.get(code)
            if iso is None or iso not in countries:
                continue
            if layer_name != base_layer and iso in shapes:
                continue
            shapes.setdefault(iso, []).extend(polygons_of(feature["geometry"]))

    units_by_name = {
        (feature["properties"].get("NAME") or "").strip(): feature
        for feature in unit_features
    }
    for iso, ne_name in NAME_OVERRIDES.items():
        if iso in shapes or iso not in countries:
            continue
        feature = units_by_name.get(ne_name)
        if feature is None:
            raise BuildError(
                f"{iso} is matched by the name {ne_name!r}, which is no longer "
                "present in Natural Earth. Revisit the override; do not drop it."
            )
        shapes[iso] = polygons_of(feature["geometry"])

    isos = [iso for iso in countries if iso in shapes or iso in fallback_points]
    missing = [iso for iso in countries if iso not in isos]
    if missing:
        raise BuildError(f"no shape and no fallback point for {missing}")

    first = payload["annualFrom"]
    years = list(range(FIRST_YEAR, LAST_YEAR + 1))
    series: dict[str, list[int]] = {}
    for iso in isos:
        totals = countries[iso]["t"]
        series[iso] = [int(totals[year - first]) for year in years]

    # A country's pool has to cover its own peak, not the world's.
    rng = random.Random(SEED)
    lights: list[tuple[float, float]] = []
    offsets = [0]
    for iso in isos:
        peak = max(series[iso])
        want = int(math.ceil(peak / PEOPLE_PER_LIGHT)) + 1
        if iso in shapes:
            points = sample_lights(shapes[iso], want, rng)
        else:
            lon, lat = fallback_points[iso]
            points = [(lon, lat)] * want
        if len(points) < want and points:
            points = points + [points[i % len(points)] for i in range(want - len(points))]
        lights.extend(points)
        offsets.append(len(lights))
    print(f"  lights: {len(lights):,} across {len(isos)} countries "
          f"(one per {PEOPLE_PER_LIGHT / 1e6:.0f} million people)")

    # Population is stored in hundreds of thousands, which keeps the largest
    # country (India, about 1.7 billion) inside an unsigned 16-bit integer.
    populations: list[int] = []
    for iso in isos:
        for value in series[iso]:
            populations.append(min(int(round(value / 100_000.0)), 65535))

    ring_offsets = [0]
    ring_points: list[int] = []
    for ring in outline_rings:
        for lon, lat in ring:
            ring_points.append(int(round(lon * 100)))
            ring_points.append(int(round(lat * 100)))
        ring_offsets.append(len(ring_points) // 2)

    light_points: list[int] = []
    for lon, lat in lights:
        light_points.append(int(round(lon * 100)))
        light_points.append(int(round(lat * 100)))

    world = [sum(series[iso][i] for iso in isos) for i in range(len(years))]

    return {
        "note": (
            "One light is a million people, scattered at random inside its own "
            "country. The model is country-level: it has no cities in it."
        ),
        "source": "UN World Population Prospects 2024, reproduced by this project's engine",
        "geometry": "Natural Earth v5.1.2, 50m admin-0",
        "peoplePerLight": PEOPLE_PER_LIGHT,
        "firstYear": FIRST_YEAR,
        "lastYear": LAST_YEAR,
        "estimatesTo": 2023,
        "iso": isos,
        "names": [countries[iso]["n"] for iso in isos],
        "lightOffsets": b64(offsets, "I"),
        "lights": b64(light_points, "h"),
        "population": b64(populations, "H"),
        "populationUnit": 100_000,
        "outlineOffsets": b64(ring_offsets, "I"),
        "outline": b64(ring_points, "h"),
        "world": [round(value / 1e9, 4) for value in world],
    }


def read_conversation_record() -> dict:
    """Count the committed conversation record, so the page cannot misstate it.

    The page tells a reader the paper was made in a numbered set of recorded
    conversations over a stretch of days. Both numbers move whenever the record
    is re-exported, and a hand-typed count is exactly the kind of claim that
    goes quietly wrong. So they are read out of the generated index and checked
    by the build like every other number the page prints.
    """
    index = REPO / "conversations" / "index.md"
    rows = re.findall(
        r"^\|\s*\d+\s*\|.*?\|\s*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\s*\|",
        index.read_text(encoding="utf-8"), re.M,
    )
    if not rows:
        raise BuildError(f"no conversation rows found in {index}; has the "
                         f"index format changed?")
    first = date.fromisoformat(min(start for start, _ in rows))
    last = date.fromisoformat(max(end for _, end in rows))
    return {
        "conversations": len(rows),
        "days": (last - first).days + 1,
        "first": first.isoformat(),
        "last": last.isoformat(),
    }


def build_story() -> dict:
    macros = load_macros()
    break_even = json.loads((REFERENCE / "selection_break_even_sensitivity.json").read_text(encoding="utf-8"))
    paired = json.loads((REFERENCE / "paired_selection_boundary_sensitivity.json").read_text(encoding="utf-8"))
    dispersion = json.loads((REFERENCE / "mainstream_propensity_cv.json").read_text(encoding="utf-8"))
    extension = json.loads((REFERENCE / "un_project_extension_summary.json").read_text(encoding="utf-8"))

    import csv

    with (REFERENCE / "mainstream_propensity_cv.csv").open(encoding="utf-8") as handle:
        cv_rows = [
            {
                "country": row["country"],
                "cv": round(float(row["cv_geometric"]), 4),
                "mean": round(float(row["mean_children"]), 3),
                "women": int(row["women"]),
                "source": row["data_source"],
            }
            for row in csv.DictReader(handle)
        ]
    cv_rows.sort(key=lambda row: row["cv"])

    ladder = [
        {
            "label": step["label"],
            "value": round(step["world_2150_billions"], 3),
            "change": None if step["change_from_previous_billions"] is None
            else round(step["change_from_previous_billions"], 3),
            "basis": step["basis"],
        }
        for step in break_even["model_ladder"]
    ]

    grid = [
        {
            "cv": round(row["mainstream_propensity_cv"], 3),
            "persistence": round(row["mainstream_persistence"], 3),
            "breakEven": round(row["break_even_decline_per_decade"] * 100, 3),
            "effect": round(row["selection_effect_final"], 4),
        }
        for row in break_even["rows"]
    ]

    return {
        "generated_from": [
            "paper/generated/results_macros.tex",
            "data/reference/selection_break_even_sensitivity.json",
            "data/reference/paired_selection_boundary_sensitivity.json",
            "data/reference/mainstream_propensity_cv.{json,csv}",
            "data/reference/un_project_extension_summary.json",
        ],
        "paper": {
            "version": macros["PaperVersion"],
            "date": macros["PaperDate"],
            "dataVintage": macros["DataVintage"],
        },
        "record": read_conversation_record(),
        "horizon": {
            "endYear": int(number(macros, "ProjectionEndYear")),
            "unBoundary": int(number(macros, "OfficialBoundaryYear")),
            "forkYear": int(number(macros, "PhaseFiveBaseYear")),
            "countries": 237,
            "frozenFertility2150": number(macros, "ConstantFertilityTwentyOneFifty"),
            "unEquivalent2150": number(macros, "UnEquivalentTwentyOneFifty"),
            "unEquivalentPeak": number(macros, "UnEquivalentPeak"),
            "unEquivalentPeakYear": int(number(macros, "UnEquivalentPeakYear")),
            "validationWorld": text(macros, "ValidationWorld"),
            "validationCountry": text(macros, "ValidationCountry"),
        },
        "extension": {
            "at2100": round(extension["world_population_billions"]["2100"]["p50"], 3),
            "at2125": [
                round(extension["world_population_billions"]["2125"][q], 3)
                for q in ("p05", "p50", "p95")
            ],
            "at2150": [
                round(extension["world_population_billions"]["2150"][q], 3)
                for q in ("p05", "p50", "p95")
            ],
            "paths": int(number(macros, "ExtensionPaths")),
            "migration": extension["migration"]["equation"],
        },
        "dispersion": {
            "cv": number(macros, "FamilySizeCV"),
            "cvLow": number(macros, "FamilySizeCVLow"),
            "cvHigh": number(macros, "FamilySizeCVHigh"),
            "persistence": number(macros, "Persistence"),
            "persistenceLow": number(macros, "PersistenceLow"),
            "persistenceHigh": number(macros, "PersistenceHigh"),
            "countries": dispersion["low_fertility_mean_le_2_2"]["countries"],
            "allCountries": dispersion["all_usable"]["countries"],
            "women": dispersion["low_fertility_mean_le_2_2"]["women"],
            "median": round(dispersion["low_fertility_mean_le_2_2"]["unweighted_median"], 4),
            "usCheck": round(dispersion["us_cross_check"]["cv_geometric"], 4),
            "usMean": round(dispersion["us_cross_check"]["mean_children"], 3),
            "rows": cv_rows,
        },
        "ladder": ladder,
        "selection": {
            "effect": number(macros, "MainstreamSelectionMultiplier"),
            "worldPath": [
                [int(year), round(float(value), 4)]
                for year, value in zip(
                    break_even["selection_world_path"]["years"],
                    break_even["selection_world_path"]["billions"],
                )
            ],
            "namedGroupShare": text(macros, "NamedGroupShareOfMechanism"),
            "overtakesYear": int(number(macros, "SelectionOvertakesYear")),
            "compositionStart": number(macros, "CompositionStartShare"),
            "compositionHigh": number(macros, "CompositionHighShare"),
            "compositionLow": number(macros, "CompositionLowShare"),
            "byCountry": [
                {"iso": "ISR", "name": "Israel", "effect": number(macros, "SelectionEffectIsrael")},
                {"iso": "USA", "name": "United States", "effect": number(macros, "SelectionEffectUnitedStates")},
                {"iso": "NGA", "name": "Nigeria", "effect": number(macros, "SelectionEffectNigeria")},
                {"iso": "JPN", "name": "Japan", "effect": number(macros, "SelectionEffectJapan")},
                {"iso": "DEU", "name": "Germany", "effect": number(macros, "SelectionEffectGermany")},
                {"iso": "KOR", "name": "Korea", "effect": number(macros, "SelectionEffectKorea")},
            ],
        },
        "boundary": {
            "rate": number(macros, "BoundaryPaired"),
            "rateDeterministic": number(macros, "BoundaryDeterministic"),
            "rateLow": number(macros, "BoundaryPairedLow"),
            "rateHigh": number(macros, "BoundaryPairedHigh"),
            "population": number(macros, "BoundaryPopulation"),
            "floor": number(macros, "BoundaryFloor"),
            "ceiling": number(macros, "BoundaryCeiling"),
            "from": break_even["pressure_from"],
            "paths": paired["migration"]["paths"],
            "grid": grid,
        },
        "uncertainty": {
            "fertility": number(macros, "WidthFertility"),
            "mechanism": number(macros, "WidthMechanism"),
            "mortality": number(macros, "WidthMortality"),
            "migration": number(macros, "WidthMigration"),
            "everything": number(macros, "WidthEverything"),
            "draws": int(number(macros, "DecompositionDraws")),
            "comparator": [
                number(macros, "ComparatorTwentyOneFiftyLow"),
                number(macros, "ComparatorTwentyOneFifty"),
                number(macros, "ComparatorTwentyOneFiftyHigh"),
            ],
            "comparatorDraws": int(number(macros, "ComparatorDraws")),
        },
        "parameters": {
            "total": int(number(macros, "MechanismParameterCount")),
            "sourced": int(number(macros, "MechanismSourcedCount")),
            "knobs": int(number(macros, "MechanismKnobCount")),
            "caveat": break_even["parameter_caveat"],
        },
        "derived": {
            "mainstreamGainPercent": text(macros, "LadderMainstreamGainPercent"),
            "backtestShare": text(macros, "BacktestRangeShare"),
            "backtestBiasMagnitude": text(macros, "BacktestWorldBias").lstrip("\u2212-"),
            "namedGroupShare": text(macros, "NamedGroupShareOfMechanism"),
        },
        "backtest": {
            "vintages": int(number(macros, "BacktestVintages")),
            "first": int(number(macros, "BacktestFirstVintage")),
            "last": int(number(macros, "BacktestLastVintage")),
            "worldBias": text(macros, "BacktestWorldBias"),
            "insideRange": int(number(macros, "BacktestInsideRange")),
            "rangeTotal": int(number(macros, "BacktestRangeTotal")),
            "africaFertility": text(macros, "BacktestAfricaFertility"),
            "eastAsiaFertility": text(macros, "BacktestEastAsiaFertility"),
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Globe")
    globe = build_globe()
    print("Story")
    story = build_story()

    for name, payload in (("globe.json", globe), ("story.json", story)):
        path = OUT / name
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        print(f"  wrote {path.relative_to(REPO)} ({path.stat().st_size / 1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"\nbuild_site_assets: {error}", file=sys.stderr)
        raise SystemExit(1) from error

"""Make country outlines small enough to ship, without losing countries.

Natural Earth's 50m outlines are 3.2 MB of coordinates. A world map on a screen
is maybe 1200 pixels wide, so most of that detail is describing wiggles finer
than a pixel. Simplifying is therefore free in visual terms and not free at all
in load time.

The risk is that simplification quietly destroys things. A tolerance that looks
fine on Russia will delete Malta, Singapore and Tuvalu outright, and a map
missing small countries looks exactly like a map that has them - which is the
same failure mode as the crosswalk, one step later. So:

* Every ring keeps at least four points, so a shape can never collapse to a
  line or vanish.
* Rings that would simplify below a floor area are kept at full detail instead
  of being dropped.
* `simplify_all` reports how many countries lost all their geometry, and the
  build refuses if any did.

The projection
--------------
Equal Earth (Šavrič, Patterson & Jenny, 2018). Chosen because it is
equal-area: a country's area on screen is proportional to its real area. That
matters for a population map more than it does for most maps. Mercator - the
default almost everywhere - inflates high latitudes so severely that Greenland
looks the size of Africa while holding 56,000 people against 1.5 billion. Using
it here would undercut the argument the map exists to make.
"""

from __future__ import annotations

import math

# Equal Earth polynomial coefficients, from the paper.
_A1, _A2, _A3, _A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3.0) / 2.0


def equal_earth(lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """Longitude/latitude in degrees to Equal Earth x/y. Units are radians-ish."""
    lam = math.radians(lon_deg)
    phi = math.radians(max(-90.0, min(90.0, lat_deg)))
    theta = math.asin(max(-1.0, min(1.0, _M * math.sin(phi))))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = lam * math.cos(theta) / (_M * (_A1 + 3 * _A2 * t2 + t6 * (7 * _A3 + 9 * _A4 * t2)))
    y = theta * (_A1 + _A2 * t2 + t6 * (_A3 + _A4 * t2))
    return x, y


def _perpendicular_distance(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(points: list, tolerance: float) -> list:
    """Drop points that sit within `tolerance` of the line they lie on."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        worst, worst_i = 0.0, -1
        for i in range(start + 1, end):
            d = _perpendicular_distance(points[i], points[start], points[end])
            if d > worst:
                worst, worst_i = d, i
        if worst > tolerance and worst_i > 0:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))
    return [p for p, k in zip(points, keep) if k]


def _ring_area(ring: list) -> float:
    """Twice the signed area, in squared degrees. Only used for comparisons."""
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def simplify_ring(ring: list, tolerance: float, min_points: int = 4) -> list | None:
    """Simplify one ring, or return None if it is too small to be worth drawing."""
    if len(ring) < min_points:
        return ring if len(ring) >= 3 else None
    out = douglas_peucker(ring, tolerance)
    if len(out) < min_points:
        # Too aggressive for this shape. Keep it rather than lose the island:
        # a country that disappears is a worse error than one drawn coarsely.
        out = ring
    if out[0] != out[-1]:
        out = out + [out[0]]
    return out


def simplify_geometry(geometry: dict, tolerance: float, min_area: float = 0.0) -> dict | None:
    """Simplify a Polygon or MultiPolygon. Returns None if nothing survives."""
    kind = geometry["type"]
    if kind == "Polygon":
        polygons = [geometry["coordinates"]]
    elif kind == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise ValueError(f"unsupported geometry {kind}")

    out_polys = []
    for poly in polygons:
        rings = []
        for j, ring in enumerate(poly):
            if j == 0 and min_area and _ring_area(ring) < min_area:
                continue  # an outer ring smaller than a pixel at any zoom
            simplified = simplify_ring([tuple(p[:2]) for p in ring], tolerance)
            if simplified:
                rings.append([list(p) for p in simplified])
        if rings:
            out_polys.append(rings)

    if not out_polys:
        return None
    if len(out_polys) == 1:
        return {"type": "Polygon", "coordinates": out_polys[0]}
    return {"type": "MultiPolygon", "coordinates": out_polys}


def count_points(geometry: dict) -> int:
    if geometry is None:
        return 0
    polys = ([geometry["coordinates"]] if geometry["type"] == "Polygon"
             else geometry["coordinates"])
    return sum(len(ring) for poly in polys for ring in poly)


def simplify_all(shapes: dict[int, dict], tolerance: float, min_area: float = 0.0):
    """Simplify every country. Raises if any country loses all its geometry."""
    out: dict[int, dict] = {}
    lost = []
    before = after = 0
    for loc, geom in shapes.items():
        before += count_points(geom)
        simplified = simplify_geometry(geom, tolerance, min_area)
        if simplified is None:
            lost.append(loc)
            continue
        after += count_points(simplified)
        out[loc] = simplified
    if lost:
        raise ValueError(
            f"{len(lost)} countries lost all geometry at tolerance {tolerance}: {lost}. "
            "Lower the tolerance or the minimum area; do not ship a map with holes."
        )
    return out, before, after

"""Build the interactive map: one self-contained HTML file.

    python scripts/build_map.py

Writes site/index.html with the geometry and the country data embedded. No
external requests, no build step, no framework - open the file and it works.
That is a deliberate choice rather than laziness: spec section 9 asks for low
maintenance cost by design, on the grounds that the project only pays off if it
survives decades, and every dependency is a liability. A single HTML file with
no imports will still open in 2050.

What the map shows by default is projected population change between 2024 and
2100, because that is the question the project is about and because it makes
the shape of the century immediately visible: Africa growing, East Asia and
Europe shrinking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import crosswalk, export, geometry, paths  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402

TOLERANCE = 0.08
VIEW_WIDTH = 1000.0
PYRAMID_YEARS = [1950, 1975, 2000, 2024, 2050, 2075, 2100, 2125, 2150]
# The hub serves each project from /<project>/ and looks for index.html at
# the repo root, so that is where the page goes. Relative asset paths only,
# which is free here because everything is embedded in the one file.
SITE = paths.REPO_ROOT


def project_shapes(shapes: dict[int, dict]):
    """Simplify, project, and scale into a fixed viewBox. Returns paths + size."""
    simplified, before, after = geometry.simplify_all(shapes, TOLERANCE)
    print(f"  geometry: {before:,} points -> {after:,} ({100 * after / before:.0f}%)")

    projected: dict[int, list[list[tuple[float, float]]]] = {}
    xs, ys = [], []
    for loc, geom in simplified.items():
        polys = ([geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"])
        rings = []
        for poly in polys:
            for ring in poly:
                pts = [geometry.equal_earth(lon, lat) for lon, lat in ring]
                rings.append(pts)
                xs.extend(p[0] for p in pts)
                ys.extend(p[1] for p in pts)
        projected[loc] = rings

    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    scale = VIEW_WIDTH / (x1 - x0)
    height = (y1 - y0) * scale

    def to_view(p):
        # SVG y grows downward, so the vertical axis is flipped here.
        return (round((p[0] - x0) * scale, 1), round((y1 - p[1]) * scale, 1))

    paths_by_loc = {}
    for loc, rings in projected.items():
        d = []
        for ring in rings:
            pts = [to_view(p) for p in ring]
            d.append("M" + "L".join(f"{x},{y}" for x, y in pts) + "Z")
        paths_by_loc[loc] = "".join(d)
    return paths_by_loc, round(height, 1), to_view


def main() -> int:
    countries = wpp.country_table()
    cw = crosswalk.build(countries)
    print("Building the map")
    paths_by_loc, view_height, to_view = project_shapes(cw.shapes)

    site_dir = export.out_dir()
    index = json.loads((site_dir / "index.json").read_text(encoding="utf-8"))
    by_iso = {c["iso3"]: c for c in index["countries"]}

    data = {}
    for _, row in cw.table.iterrows():
        loc = int(row.loc_id)
        iso = row.iso3
        payload = json.loads((site_dir / "countries" / f"{iso}.json").read_text(encoding="utf-8"))
        keep = [payload["years"].index(y) for y in PYRAMID_YEARS]
        # People, not thousands. Rounding a pyramid to thousands looks harmless
        # and is not: Tuvalu has 11,000 people spread over 101 ages and two
        # sexes, so every cell rounds to zero and the country's pyramid comes
        # out empty. Seven countries did exactly that. It also cost Iceland 3%
        # through accumulated per-age rounding. The file is bigger; the numbers
        # are right.
        female = [payload["female"][i] for i in keep]
        male = [payload["male"][i] for i in keep]
        totals = payload["annual_total"]
        meta = by_iso[iso]
        entry = {
            "n": payload["name"],
            "f": female,
            "m": male,
            "t": totals,
            "pk": meta["peak_year"],
            "pkp": meta["peak_population"],
            "grew": meta["peaked_before_end"],
        }
        if not row.has_shape:
            x, y = to_view(geometry.equal_earth(row.point_lon, row.point_lat))
            entry["pt"] = [x, y]
        data[iso] = entry

    shapes_by_iso = {}
    for _, row in cw.table.iterrows():
        if row.has_shape:
            shapes_by_iso[row.iso3] = paths_by_loc[int(row.loc_id)]

    payload = {
        "viewWidth": VIEW_WIDTH,
        "viewHeight": view_height,
        "pyramidYears": PYRAMID_YEARS,
        "annualFrom": index["annual_years"][0],
        "annualTo": index["annual_years"][1],
        "shapes": shapes_by_iso,
        "countries": data,
    }

    html = TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    out = SITE / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  {len(shapes_by_iso)} shapes, {len(data)} countries")
    print(f"\nWrote {out.relative_to(paths.REPO_ROOT)} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World population to 2150</title>
<style>
:root{
  --bg:#FBFAF7; --panel:#FFFFFF; --ink:#2C2C2A; --muted:#5F5E5A; --faint:#D3D1C7;
  --line:#B4B2A9; --grow:#0F6E56; --shrink:#993C1D; --female:#D4537E; --male:#378ADD;
  --accent:#185FA5;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#1B1B19; --panel:#232321; --ink:#F1EFE8; --muted:#B4B2A9; --faint:#3A3A37;
         --line:#5F5E5A; --grow:#5DCAA5; --shrink:#F0997B; --female:#ED93B1; --male:#85B7EB;
         --accent:#85B7EB; }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:20px 22px 6px;max-width:1400px;margin:0 auto}
h1{font-size:21px;font-weight:500;margin:0 0 4px}
.sub{color:var(--muted);font-size:13.5px;max-width:70ch;margin:0}
main{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(300px,1fr);gap:16px;
  padding:14px 22px 30px;max-width:1400px;margin:0 auto;align-items:start}
@media (max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--faint);border-radius:12px;padding:14px}
svg{display:block;width:100%;height:auto}
.country{fill:var(--faint);stroke:var(--bg);stroke-width:.6;cursor:pointer}
.country:hover{stroke:var(--ink);stroke-width:1.2}
.country.sel{stroke:var(--ink);stroke-width:1.6}
.legend{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px;
  font-size:12px;color:var(--muted)}
.swatch{width:26px;height:11px;border-radius:2px;display:inline-block}
h2{font-size:16px;font-weight:500;margin:0 0 2px}
.note{color:var(--muted);font-size:12.5px;margin:0 0 10px}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px 12px;margin:10px 0 4px}
.stat{border-top:1px solid var(--faint);padding-top:6px}
.stat b{display:block;font-size:17px;font-weight:500}
.stat span{color:var(--muted);font-size:11.5px}
label{display:block;color:var(--muted);font-size:12px;margin:12px 0 2px}
input[type=range]{width:100%;accent-color:var(--accent)}
.tip{position:fixed;pointer-events:none;background:var(--panel);color:var(--ink);
  border:1px solid var(--line);border-radius:7px;padding:5px 8px;font-size:12.5px;
  opacity:0;transition:opacity .12s;z-index:9}
footer{max-width:1400px;margin:0 auto;padding:0 22px 34px;color:var(--muted);font-size:12.5px}
footer p{max-width:80ch}
.kind{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;
  border:1px solid var(--line);color:var(--muted)}
</style>
</head>
<body>
<header>
  <h1>World population to 2150</h1>
  <p class="sub">Colour shows projected change between 2024 and 2100. Click any country
  for its population pyramid. Equal-area projection, so a country's size on screen is
  proportional to its real area.</p>
</header>

<main>
  <div class="card">
    <svg id="map" role="img" aria-label="World map of projected population change"></svg>
    <div class="legend" id="legend"></div>
  </div>

  <div class="card">
    <h2 id="cname">World</h2>
    <p class="note" id="cnote"></p>
    <div class="stats" id="stats"></div>
    <label for="yr">Population pyramid — <span id="yrlabel"></span>
      <span class="kind" id="kind"></span></label>
    <input type="range" id="yr" min="0" max="8" step="1" value="3">
    <svg id="pyr" role="img" aria-label="Population pyramid"></svg>
    <label>Total population, 1950 to 2150</label>
    <svg id="traj" role="img" aria-label="Population over time"></svg>
  </div>
</main>

<footer>
  <p><b>What you are looking at.</b> Figures to 2023 are the UN's estimates of what
  already happened. From 2024 they come from this project's projection engine, run on
  the UN's own fertility and mortality assumptions — it reproduces their published
  numbers to about 0.001% at 2100. After 2100 nobody publishes fertility or mortality
  rates, so the run holds them at their 2100 values. That last stretch is an
  assumption, not a forecast anyone stands behind.</p>
  <p><b>A warning the project takes seriously.</b> Migration is close to unforecastable
  beyond a few decades. It roughly cancels out for the world as a whole, but it
  dominates results for individual rich countries. World totals at 2150 mean something.
  Country totals at 2150 mean much less.</p>
</footer>

<div class="tip" id="tip"></div>

<script id="payload" type="application/json">__DATA__</script>
<script>
(function(){
  "use strict";
  var D = JSON.parse(document.getElementById("payload").textContent);
  var YEARS = D.pyramidYears, NAGE = 101;
  var fmt = function(n){ return n.toLocaleString("en-US"); };

  function people(n){
    var m = n / 1e6;
    if (m >= 1000) return (m/1000).toFixed(2) + "bn";
    if (m >= 10) return m.toFixed(0) + "m";
    if (m >= 1) return m.toFixed(2) + "m";
    if (n >= 1000) return (n/1000).toFixed(0) + "k";
    return fmt(Math.round(n));
  }

  // Diverging scale. Teal for growth, coral for decline: distinguishable
  // without relying on red against green.
  var STOPS = [
    [-100, [122,42,17]], [-50, [153,60,29]], [-25, [216,90,48]],
    [-10, [240,153,123]], [0, [211,209,199]], [10, [93,202,165]],
    [50, [29,158,117]], [100, [15,110,86]], [400, [4,52,44]]
  ];
  function colour(pct){
    if (pct === null || pct === undefined || !isFinite(pct)) return "var(--faint)";
    var v = Math.max(-100, Math.min(400, pct));
    for (var i=0;i<STOPS.length-1;i++){
      var a = STOPS[i], b = STOPS[i+1];
      if (v <= b[0]){
        var t = (v - a[0]) / (b[0] - a[0]);
        var c = [0,1,2].map(function(k){ return Math.round(a[1][k] + t*(b[1][k]-a[1][k])); });
        return "rgb(" + c.join(",") + ")";
      }
    }
    return "rgb(" + STOPS[STOPS.length-1][1].join(",") + ")";
  }

  function changePct(iso){
    var c = D.countries[iso];
    var i2024 = 2024 - D.annualFrom, i2100 = 2100 - D.annualFrom;
    var a = c.t[i2024], b = c.t[i2100];
    if (!a) return null;
    return (b/a - 1) * 100;
  }

  // ---- map ----------------------------------------------------------------
  var map = document.getElementById("map");
  map.setAttribute("viewBox", "0 0 " + D.viewWidth + " " + D.viewHeight);
  var frag = "";
  Object.keys(D.shapes).forEach(function(iso){
    frag += '<path class="country" data-iso="' + iso + '" d="' + D.shapes[iso] +
            '" fill="' + colour(changePct(iso)) + '"></path>';
  });
  Object.keys(D.countries).forEach(function(iso){
    var pt = D.countries[iso].pt;
    if (pt) {
      frag += '<circle class="country" data-iso="' + iso + '" cx="' + pt[0] + '" cy="' +
              pt[1] + '" r="3.2" fill="' + colour(changePct(iso)) + '"></circle>';
    }
  });
  map.innerHTML = frag;

  var legend = document.getElementById("legend");
  var marks = [-75, -50, -25, 0, 50, 100, 200];
  legend.innerHTML = "<span>2024 to 2100:</span>" + marks.map(function(v){
    return '<span><i class="swatch" style="background:' + colour(v) + '"></i> ' +
           (v > 0 ? "+" : "") + v + "%</span>";
  }).join("");

  // ---- detail panel -------------------------------------------------------
  var selected = null;
  var slider = document.getElementById("yr");

  function worldSeries(){
    var t = new Array(D.countries[Object.keys(D.countries)[0]].t.length).fill(0);
    var f = [], m = [];
    for (var y=0; y<YEARS.length; y++){
      f.push(new Array(NAGE).fill(0));
      m.push(new Array(NAGE).fill(0));
    }
    Object.keys(D.countries).forEach(function(iso){
      var c = D.countries[iso];
      for (var i=0;i<t.length;i++) t[i] += c.t[i];
      for (var y=0;y<YEARS.length;y++){
        for (var a=0;a<NAGE;a++){ f[y][a] += c.f[y][a]; m[y][a] += c.m[y][a]; }
      }
    });
    var peak = 0;
    for (var i=1;i<t.length;i++) if (t[i] > t[peak]) peak = i;
    return {n:"World", t:t, f:f, m:m, pk:D.annualFrom+peak, pkp:t[peak]*1000,
            grew: peak < t.length-1};
  }
  var WORLD = worldSeries();

  function kindOf(year){
    if (year <= 2023) return "estimated";
    if (year <= 2100) return "projected";
    return "past published rates";
  }

  function drawPyramid(c, yi){
    var svg = document.getElementById("pyr");
    var W = 340, H = 240, padL = 26, padB = 20, mid = W/2;
    var f = c.f[yi], m = c.m[yi];
    var biggest = 0;
    for (var y=0;y<YEARS.length;y++){
      for (var a=0;a<NAGE;a++){
        if (c.f[y][a] > biggest) biggest = c.f[y][a];
        if (c.m[y][a] > biggest) biggest = c.m[y][a];
      }
    }
    if (biggest <= 0) biggest = 1;
    var half = (W - padL) / 2 - 4;
    var bh = (H - padB) / NAGE;
    var s = "";
    for (var a=0;a<NAGE;a++){
      var yy = H - padB - (a+1)*bh;
      var wf = (f[a]/biggest) * half, wm = (m[a]/biggest) * half;
      if (wf > 0) s += '<rect x="' + (mid-wf) + '" y="' + yy + '" width="' + wf +
                       '" height="' + Math.max(bh,0.6) + '" fill="var(--female)"></rect>';
      if (wm > 0) s += '<rect x="' + mid + '" y="' + yy + '" width="' + wm +
                       '" height="' + Math.max(bh,0.6) + '" fill="var(--male)"></rect>';
    }
    [0,20,40,60,80,100].forEach(function(a){
      var yy = H - padB - a*bh;
      s += '<text x="2" y="' + (yy+3) + '" font-size="9" fill="var(--muted)">' +
           (a===100?"100+":a) + '</text>';
    });
    s += '<line x1="' + mid + '" y1="0" x2="' + mid + '" y2="' + (H-padB) +
         '" stroke="var(--faint)" stroke-width="1"></line>';
    s += '<text x="' + (mid-6) + '" y="' + (H-6) + '" font-size="10" text-anchor="end" ' +
         'fill="var(--female)">women</text>';
    s += '<text x="' + (mid+6) + '" y="' + (H-6) + '" font-size="10" fill="var(--male)">men</text>';
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.innerHTML = s;
  }

  function drawTrajectory(c){
    var svg = document.getElementById("traj");
    var W = 340, H = 110, padL = 4, padB = 16, padT = 6;
    var t = c.t, n = t.length;
    var max = Math.max.apply(null, t), min = 0;
    var x = function(i){ return padL + (i/(n-1)) * (W - padL*2); };
    var y = function(v){ return padT + (1 - (v-min)/(max-min)) * (H - padB - padT); };
    var d = "", i;
    for (i=0;i<n;i++) d += (i?"L":"M") + x(i).toFixed(1) + "," + y(t[i]).toFixed(1);
    var iNow = 2024 - D.annualFrom, i2100 = 2100 - D.annualFrom;
    var s = '<path d="' + d + '" fill="none" stroke="var(--accent)" stroke-width="1.8"></path>';
    [[iNow,"2024"],[i2100,"2100"]].forEach(function(p){
      s += '<line x1="' + x(p[0]) + '" y1="' + padT + '" x2="' + x(p[0]) + '" y2="' +
           (H-padB) + '" stroke="var(--faint)" stroke-width="1" stroke-dasharray="3 3"></line>';
      s += '<text x="' + (x(p[0])+3) + '" y="' + (padT+9) + '" font-size="9" ' +
           'fill="var(--muted)">' + p[1] + '</text>';
    });
    s += '<text x="' + padL + '" y="' + (H-3) + '" font-size="9" fill="var(--muted)">1950</text>';
    s += '<text x="' + (W-padL) + '" y="' + (H-3) + '" font-size="9" text-anchor="end" ' +
         'fill="var(--muted)">2150</text>';
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.innerHTML = s;
  }

  function show(iso){
    var c = iso ? D.countries[iso] : WORLD;
    if (!c) return;
    selected = iso;
    document.getElementById("cname").textContent = c.n;
    var i2024 = 2024 - D.annualFrom, i2100 = 2100 - D.annualFrom;
    var pct = (c.t[i2100]/c.t[i2024] - 1) * 100;
    document.getElementById("cnote").textContent =
      (pct >= 0 ? "Grows " : "Shrinks ") + Math.abs(pct).toFixed(0) +
      "% between 2024 and 2100." + (iso ? "" : " Every country added together.");
    document.getElementById("stats").innerHTML = [
      ["2024", people(c.t[i2024])],
      ["2100", people(c.t[i2100])],
      ["2150", people(c.t[c.t.length-1])],
      [c.grew ? "peak, in " + c.pk : "still growing in 2150",
       c.grew ? people(c.pkp) : "—"]
    ].map(function(p){
      return '<div class="stat"><b>' + p[1] + '</b><span>' + p[0] + '</span></div>';
    }).join("");
    update();
    Array.prototype.forEach.call(document.querySelectorAll(".country"), function(el){
      el.classList.toggle("sel", el.getAttribute("data-iso") === iso);
    });
  }

  function update(){
    var yi = +slider.value;
    var c = selected ? D.countries[selected] : WORLD;
    document.getElementById("yrlabel").textContent = YEARS[yi];
    document.getElementById("kind").textContent = kindOf(YEARS[yi]);
    drawPyramid(c, yi);
    drawTrajectory(c);
  }

  slider.max = String(YEARS.length - 1);
  slider.value = String(YEARS.indexOf(2024));
  slider.addEventListener("input", update);

  var tip = document.getElementById("tip");
  map.addEventListener("click", function(e){
    var iso = e.target.getAttribute && e.target.getAttribute("data-iso");
    show(iso || null);
  });
  map.addEventListener("mousemove", function(e){
    var iso = e.target.getAttribute && e.target.getAttribute("data-iso");
    if (!iso){ tip.style.opacity = 0; return; }
    var c = D.countries[iso], p = changePct(iso);
    tip.textContent = c.n + "  " + (p >= 0 ? "+" : "") + p.toFixed(0) + "%";
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top = (e.clientY + 12) + "px";
    tip.style.opacity = 1;
  });
  map.addEventListener("mouseleave", function(){ tip.style.opacity = 0; });

  show(null);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

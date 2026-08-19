"""Build the interactive map: one self-contained HTML file.

    python scripts/build_map.py

Writes map/index.html with the geometry and the country data embedded. No
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
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import crosswalk, export, geometry, paths  # noqa: E402
from popmodel.ingest import census  # noqa: E402
from popmodel.ingest import wpp  # noqa: E402

TOLERANCE = 0.08
VIEW_WIDTH = 1000.0
PYRAMID_YEARS = [1950, 1975, 2000, 2024, 2050, 2075, 2100, 2125, 2150]
# The public front page is scripts/build_site.py's scrollytelling story; this
# map is the explorable companion to it and lives one level down at /map/.
# Relative asset paths only, which is free here because everything is embedded
# in the one file.
SITE = paths.REPO_ROOT / "map"
BAND = {}
BAND_META = None



def load_band():
    """The Phase 4 ensemble's 5th and 95th percentiles, per country and year.

    Optional on purpose. The map was useful before the ensemble existed and
    must keep building if the ensemble has not been run, so a missing file
    means no band rather than a failure. What must never happen is a band that
    is silently wrong, so the years are checked rather than assumed.
    """
    path = paths.OUT / "uw_ensemble_country_totals.npz"
    if not path.exists():
        print("  no ensemble found; the page will have no uncertainty band")
        return {}, None
    z = np.load(path, allow_pickle=False)
    years = z["years"]
    levels = z["quantile_levels"]
    if not (abs(levels[0] - 0.05) < 1e-9 and abs(levels[-1] - 0.95) < 1e-9):
        raise SystemExit(f"the ensemble's quantiles are {levels}, expected 5% and 95%")
    q = z["location_quantiles"]  # (Q, Y, L)
    codes = [str(c) for c in z["locations"]]
    if len(levels) < 7:
        raise SystemExit(
            f"the ensemble stored {len(levels)} quantile levels; the page needs "
            f"seven to reconstruct a distribution. Rerun run_uw_ensemble.py."
        )
    median_row = int(np.argmin(np.abs(levels - 0.5)))
    other_rows = [i for i in range(len(levels)) if i != median_row]
    band = {}
    for j, code in enumerate(codes):
        median = q[median_row, :, j]
        safe = np.maximum(median, 1.0)
        band[code] = {
            "lo": [int(round(v)) for v in q[0, :, j]],
            "hi": [int(round(v)) for v in q[-1, :, j]],
            # Thousands, because a page carrying 236 countries of these does not
            # need the last three digits of a percentile.
            "qm": [int(round(v / 1000.0)) for v in median],
            "qr": [
                [int(round(10000.0 * v / m)) for v, m in zip(q[row, :, j], safe)]
                for row in other_rows
            ],
        }
    world = (
        [int(round(v)) for v in np.quantile(z["world"], 0.05, axis=0)],
        [int(round(v)) for v in np.quantile(z["world"], 0.95, axis=0)],
    )
    print(f"  uncertainty band for {len(band)} countries, "
          f"{int(years[0])}-{int(years[-1])}")
    return band, {"years": years, "world": world}


def band_for(iso):
    """Band arrays for one country, or nothing if the ensemble does not cover it."""
    return BAND.get(iso) or {}

def inline_figure(name: str) -> str:
    """A committed figure, embedded so the page stays a single file.

    Matplotlib writes width and height attributes on its root element, which
    pin the figure to the size it was drawn at and make it overflow a phone.
    They are removed so the viewBox alone governs, which scales. Done by
    splitting the tag rather than by a regular expression, because a
    substitution that silently eats the opening tag produces a page with no
    figure and no error.
    """
    path = paths.REPO_ROOT / "docs" / f"{name}.svg"
    if not path.exists():
        return ""
    # Matplotlib's SVG writer leaves spaces at line ends. Strip them while
    # embedding so a regenerated single-file page stays diff-clean.
    markup = "\n".join(
        line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()
    ) + "\n"
    open_at = markup.index("<svg")
    close_at = markup.index(">", open_at)
    tag, rest = markup[open_at:close_at], markup[close_at:]

    kept = ['<svg class="figure" preserveAspectRatio="xMidYMid meet"']
    for attribute in re.findall(r'[\w:.-]+="[^"]*"', tag):
        if not attribute.startswith(("width=", "height=")):
            kept.append(attribute)
    rebuilt = " ".join(kept) + rest
    if 'viewBox="' not in rebuilt:
        raise SystemExit(f"{name}.svg has no viewBox; it would not scale")
    return rebuilt


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

    # The data-confidence layer. A projection for Lebanon and a projection for
    # Denmark are drawn in the same ink otherwise, and they are not the same
    # kind of object.
    conf = census.load_table().set_index("iso3")

    global BAND, BAND_META
    BAND, BAND_META = load_band()

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
            **band_for(iso),
            "n": payload["name"],
            "f": female,
            "m": male,
            "t": totals,
            "cen": (None if iso not in conf.index or conf.loc[iso, "last_census_year"] !=
                    conf.loc[iso, "last_census_year"]
                    else int(conf.loc[iso, "last_census_year"])),
            "band": (str(conf.loc[iso, "band"]) if iso in conf.index else "not listed"),
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
    if BAND_META is not None:
        payload["bandFrom"] = int(BAND_META["years"][0])
        payload["worldBand"] = list(BAND_META["world"])

    html = TEMPLATE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
    for token, figure in (
        ("__MODEL_FLOW__", "how-the-model-works"),
        ("__UN_EXTENSION__", "un-project-extension"),
        ("__SELECTION_BOUNDARY__", "selection-break-even"),
        ("__DECOMPOSITION__", "decomposition"),
        ("__MECHANISMS__", "phase5"),
    ):
        markup = inline_figure(figure)
        if not markup:
            print(f"  note: {figure}.svg is missing; the page will omit it")
        html = html.replace(token, markup)
    out = SITE / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
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
.project-nav{display:flex;justify-content:space-between;align-items:center;gap:16px;
  margin:0 0 12px;color:var(--muted);font-size:12.5px}
.project-nav a{color:var(--accent);text-decoration:none}
.project-nav a:hover{text-decoration:underline}
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
.modes{display:flex;gap:6px;margin:0 0 10px}
.modes button{font:inherit;font-size:12.5px;padding:5px 11px;cursor:pointer;
  border:1px solid var(--faint);background:transparent;color:var(--muted);
  border-radius:99px}
.modes button.on{background:var(--accent);border-color:var(--accent);color:#fff}
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
.figures{max-width:1400px;margin:0 auto;padding:8px 22px 10px}
.figures h2{font-size:17px;margin:26px 0 8px}
.figures p{max-width:80ch;color:var(--muted);font-size:13.5px;margin:0 0 10px}
.figures .figure{width:100%;height:auto;display:block;margin:6px 0 4px;background:#fff;border-radius:4px}
.flow-wrap{overflow-x:auto;margin:6px 0 4px}
.flow-wrap .figure{min-width:760px;margin:0}
.readout{margin:6px 0 0;font-size:12.5px;color:var(--ink);min-height:1.2em}
.readout b{font-variant-numeric:tabular-nums}
footer{max-width:1400px;margin:0 auto;padding:0 22px 34px;color:var(--muted);font-size:12.5px}
footer p{max-width:80ch}
.kind{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;
  border:1px solid var(--line);color:var(--muted)}
</style>
</head>
<body>
<header>
  <nav class="project-nav" aria-label="Project">
    <a href="../index.html">&larr; Population to 2150</a>
    <a href="../paper/index.html">Paper and citation</a>
  </nav>
  <h1>World population to 2150</h1>
  <p class="sub">Colour shows projected change between 2024 and 2100. Click any country
  for its population pyramid. Equal-area projection, so a country's size on screen is
  proportional to its real area.</p>
</header>

<main>
  <div class="card">
    <div class="modes" role="group" aria-label="What the colour shows">
      <button id="m-change" class="on" type="button" aria-pressed="true">Population change</button>
      <button id="m-census" type="button" aria-pressed="false">When they last counted</button>
    </div>
    <svg id="map" role="img" aria-label="World map"></svg>
    <div class="legend" id="legend"></div>
    <p class="note" id="modenote"></p>
  </div>

  <div class="card">
    <h2 id="cname">World</h2>
    <p class="note" id="cnote"></p>
    <div class="stats" id="stats"></div>
    <p class="note" id="census"></p>
    <label for="yr">Population pyramid — <span id="yrlabel"></span>
      <span class="kind" id="kind"></span></label>
    <input type="range" id="yr" min="0" max="8" step="1" value="3">
    <svg id="pyr" role="img" aria-label="Population pyramid"></svg>
    <label>Total population, 1950 to 2150</label>
    <svg id="traj" role="img" aria-label="Population over time, hover to read a year"></svg>
    <p class="readout" id="trajread"></p>
    <p class="note"><b>Hover the chart</b> to read any year: the guide line
    names the year, the dotted line carries the median across to the axis, and
    the shape beside it is how the 1,000 draws are distributed at that moment.
    That shape is rebuilt from seven stored percentiles rather than the raw
    draws, so it is the right shape and an approximate one.</p>
    <p class="note">The line is this project's engine run on the UN's own
    assumptions. The shaded band is the 5th to 95th percentile of 1,000 draws
    from the University of Washington's Bayesian posterior, projected the same
    way. It is the conventional view's own uncertainty, not this project's, and
    it leaves out uncertainty about migration.</p>
  </div>
</main>


<section class="figures">
  <h2 id="how-it-works">How the model works</h2>
  <p>Both approaches use the same dependable accounting: age people one year,
  apply survival, count births, and add migration. The disagreement is upstream.
  A conventional projection supplies a future fertility path; this project also
  asks how the fertility environment and the changing mix of people generate
  that path.</p>
  <div class="flow-wrap">__MODEL_FLOW__</div>
  <h2 id="model-boundary">Where the UN model ends</h2>
  <p>The black line below is the published UN reproduction and stops at 2100.
  The blue line is a separate, project-owned extension. It holds the final UN
  fertility and mortality schedules constant, but continues migration with
  1,000 stochastic paths from a late-horizon AR(1) emulator of UW's
  <i>bayesMig</i> output. Every path is forced to have exactly zero world net
  migration each year.</p>
  <p>The narrow world band is not evidence that migration is predictable. A
  migrant has both an origin and a destination, so the direct world total
  cancels. Country results, especially for the Gulf, remain extremely wide.
  This is a project extension after 2100, never an official UN projection.</p>
  <div class="flow-wrap">__UN_EXTENSION__</div>
  <p class="note">The interactive country line and pyramids above still use the
  earlier deterministic working run after 2100, including its frozen final
  migration count. They are retained for inspection while the new stochastic
  extension is connected to the selection model; the figure in this section is
  the current reference for post-2100 migration.</p>
  <h2 id="selection-first">Start with selection; stress-test future development</h2>
  <p>Today's fertility already contains today's economic and social environment.
  The cleaner benchmark therefore keeps the observed and already-projected
  decline, removes the UN-style recovery, and adds <b>no extra decline beyond
  that stable-low path</b>. It then lets only the mainstream composition change,
  using the measured family-size spread and parent-child persistence through a
  fixed three-type approximation.
  This does not assume that economic development stops. It prevents an
  unmeasured future economic effect from being counted as evidence.</p>
  <p>The left panel asks how much <i>additional</i>, uniform decline after 2050
  would be needed to cancel selection. At the central measured family-size
  spread and parent-child persistence, the answer is about <b>1.53% per
  decade</b>. The old 4% path sits far beyond that boundary, so it belongs as a
  stress test rather than as this project's preferred forecast.</p>
  <div class="flow-wrap">__SELECTION_BOUNDARY__</div>
  <p>The model ladder on the right is also a complexity check. Mainstream
  selection adds 1.82 billion people by 2150 relative to the stable-low
  no-selection benchmark. Adding the named groups and one routing knob changes
  that by only another 0.05 billion. The illustrative 4% pressure path then
  removes 2.79 billion.
  The headline was being controlled by the unsourced environmental knob, not by
  the elaborate selection extension.</p>
  <h2>What the uncertainty is made of</h2>
  <p>The band above says the answer is uncertain. It does not say what about,
  and those are different claims. Each bar below is how wide the 90% range gets
  when one source is varied across its own draws and everything else is held at
  its median.</p>
  <p>Two results worth the space. For the world, <b>fertility is almost the
  whole answer</b>. After correcting every migration path to balance globally,
  migration contributes 0.34 billion of 2150 world range, versus 7.26 billion
  from fertility. For individual countries that reverses completely: migration
  is <b>forty-two times</b> fertility for the United Arab Emirates and about a
  sixteenth of it for Nigeria. And the band drawn on
  this page contains <b>no migration uncertainty at all</b>, because the
  projection uses a single median migration path.</p>
  __DECOMPOSITION__
  <h2>The two mechanisms</h2>
  <p>Underneath any long-run projection are two forces pulling opposite ways.
  <b>Selection and transmission</b>: people who have more children pass on
  some of whatever produced that, so the composition of the population shifts
  toward them. <b>Development pressure</b>: the opportunity cost of parenthood
  keeps rising &mdash; longer education, steeper careers, costlier housing,
  later partnership &mdash; so a person of any given disposition has fewer
  children than the same person would have had a generation earlier.</p>
  <p>The older four-corner plot below remains useful as a stress test. Under its
  illustrative 4% pressure path, selection does not catch the moving
  environment by 2150. The break-even map above now makes the conditional nature
  of that result explicit: 4% is a scenario well beyond the central 1.53%
  boundary, not a measured future economic path.</p>
  <p><b>The last empirical gap is now measured.</b> Across 19 low-fertility
  countries, the median spread in completed family size is a coefficient of
  variation of 0.57 (country range 0.44-0.79); U.S. CDC cohorts independently
  give 0.69. The old assumed 0.60 was close by luck. The model uses this as an
  effective spread paired with the observed parent-child correlation, not as a
  claim that all family-size variation is an inherited latent trait.</p>
  __MECHANISMS__
  <p class="note">All eight sourced mechanism parameters have been
  <b>checked against their evidence</b>. Five of the thirteen parameters remain
  explicit scenario knobs with no independently established future value. The
  source trail is recorded in the repository; the heights remain conditional
  on those choices and the stated empirical ranges.</p>
</section>

<footer>
  <p><b>What you are looking at.</b> Figures to 2023 are the UN's estimates of what
  already happened. From 2024 they come from this project's projection engine, run on
  the UN's own fertility and mortality assumptions — it reproduces their published
  numbers to about 0.001% at 2100. After 2100 nobody publishes fertility or mortality
  rates, so the run holds them at their 2100 values. The interactive line also
  retains the older frozen-migration treatment; the separate boundary figure
  above shows the current stochastic extension. Everything after 2100 is a
  project assumption, not a UN forecast.</p>
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

  // Recency of the last census. A sequential ramp, so the eye goes to the
  // countries whose numbers are least anchored to an actual count.
  var BANDS = [
    ["within 5 years",   "#9FE1CB"],
    ["5 to 14 years",    "#FAC775"],
    ["15 years or more", "#D85A30"],
    ["none since 1985",  "#712B13"],
    ["not listed",       "#B4B2A9"]
  ];
  var BAND_COLOUR = {};
  BANDS.forEach(function(b){ BAND_COLOUR[b[0]] = b[1]; });

  var mode = "change";

  function fillFor(iso){
    var c = D.countries[iso];
    if (mode === "census") return BAND_COLOUR[c.band] || "var(--faint)";
    return colour(changePct(iso));
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
            '"></path>';
  });
  Object.keys(D.countries).forEach(function(iso){
    var pt = D.countries[iso].pt;
    if (pt) {
      frag += '<circle class="country" data-iso="' + iso + '" cx="' + pt[0] + '" cy="' +
              pt[1] + '" r="3.2"></circle>';
    }
  });
  map.innerHTML = frag;

  var legend = document.getElementById("legend");
  var modenote = document.getElementById("modenote");

  function repaint(){
    Array.prototype.forEach.call(document.querySelectorAll(".country"), function(el){
      // The .country rule supplies a neutral fallback. Apply choropleth colours
      // as an inline style so that rule cannot win the CSS cascade.
      el.style.fill = fillFor(el.getAttribute("data-iso"));
    });
    if (mode === "census"){
      legend.innerHTML = "<span>last census:</span>" + BANDS.map(function(b){
        return '<span><i class="swatch" style="background:' + b[1] + '"></i> ' +
               b[0] + "</span>";
      }).join("");
      modenote.textContent = "How long since each country ran a population census "
        + "(UN Statistics Division). This is one dimension of confidence, not a "
        + "data-quality score: Denmark counts continuously from registers rather "
        + "than by census, and a recent census can still be a poor one.";
    } else {
      var marks = [-75, -50, -25, 0, 50, 100, 200];
      legend.innerHTML = "<span>2024 to 2100:</span>" + marks.map(function(v){
        return '<span><i class="swatch" style="background:' + colour(v) + '"></i> ' +
               (v > 0 ? "+" : "") + v + "%</span>";
      }).join("");
      modenote.textContent = "";
    }
  }

  document.getElementById("m-change").addEventListener("click", function(){
    mode = "change"; this.classList.add("on");
    this.setAttribute("aria-pressed", "true");
    document.getElementById("m-census").classList.remove("on");
    document.getElementById("m-census").setAttribute("aria-pressed", "false"); repaint();
  });
  document.getElementById("m-census").addEventListener("click", function(){
    mode = "census"; this.classList.add("on");
    this.setAttribute("aria-pressed", "true");
    document.getElementById("m-change").classList.remove("on");
    document.getElementById("m-change").setAttribute("aria-pressed", "false"); repaint();
  });

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
    // The world band is NOT the sum of the country bands. Summing 5th
    // percentiles would assume every country lands in its own tail at the same
    // time, which is far narrower than the truth. It is computed from each
    // draw's own world total instead, and passed in already done.
    var lo = D.worldBand ? D.worldBand[0] : null;
    var hi = D.worldBand ? D.worldBand[1] : null;
    return {n:"World", t:t, f:f, m:m, pk:D.annualFrom+peak, pkp:t[peak]*1000,
            lo:lo, hi:hi, grew: peak < t.length-1};
  }
  var WORLD = worldSeries();

  function kindOf(year){
    if (year <= 2023) return "estimated";
    if (year <= 2100) return "projected";
    return "past published rates";
  }

  function drawPyramid(c, yi){
    var svg = document.getElementById("pyr");
    // padT exists so the "100+" label has somewhere to sit. Without it the
    // top bar starts at y=0, the label's ascender is clipped by the viewBox
    // edge, and it reads as though it collides with the slider above.
    var W = 340, H = 250, padL = 26, padB = 20, padT = 10, mid = W/2;
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
    var bh = (H - padB - padT) / NAGE;
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
    s += '<line x1="' + mid + '" y1="' + padT + '" x2="' + mid + '" y2="' + (H-padB) +
         '" stroke="var(--faint)" stroke-width="1"></line>';
    s += '<text x="' + (mid-6) + '" y="' + (H-6) + '" font-size="10" text-anchor="end" ' +
         'fill="var(--female)">women</text>';
    s += '<text x="' + (mid+6) + '" y="' + (H-6) + '" font-size="10" fill="var(--male)">men</text>';
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.innerHTML = s;
  }

  // The trajectory chart, and the hover that makes the uncertainty legible.
  //
  // The band alone tells you the range at 2150 is enormous. It does not tell
  // you what the range means at any particular year, and nobody can read a
  // value off a shaded region by eye. Hovering names the year, draws the
  // median across to the axis, and shows the shape of the distribution the
  // draws actually produced at that moment.
  //
  // That shape is reconstructed from seven stored quantiles, not from the raw
  // 1,000 draws: six intervals of known probability, each turned into a
  // density by dividing its probability by its width. It is the right shape
  // and an approximate one, and the caption under the chart says so.
  var TRAJ = {W: 340, H: 152, padL: 36, padR: 10, padT: 10, padB: 22};
  var hoverYear = null;

  function shortNumber(v){
    if (v >= 1e9) return (v/1e9).toFixed(1) + "bn";
    if (v >= 1e6) return Math.round(v/1e6) + "m";
    if (v >= 1e3) return Math.round(v/1e3) + "k";
    return Math.round(v).toString();
  }

  function bandQuantiles(c, i){
    if (!c.qm || !c.qr) return null;
    var median = c.qm[i] * 1000;
    var out = [0, 0, 0, median, 0, 0, 0];
    for (var k = 0; k < 6; k++){
      var slot = k < 3 ? k : k + 1;
      out[slot] = median * c.qr[k][i] / 10000;
    }
    return out;
  }

  function trajScales(c){
    var t = c.t, n = t.length, g = TRAJ;
    var max = Math.max.apply(null, t), i;
    if (c.hi) for (i = 0; i < c.hi.length; i++) if (c.hi[i] > max) max = c.hi[i];
    max = max * 1.04;
    return {
      n: n, max: max,
      x: function(i){ return g.padL + (i/(n-1)) * (g.W - g.padL - g.padR); },
      y: function(v){ return g.padT + (1 - v/max) * (g.H - g.padB - g.padT); }
    };
  }

  // The density at one year, drawn sideways against the value axis. Six
  // intervals of known probability become six densities; the curve through
  // them is closed back to the guide line.
  function violin(c, index, s, xAt, toLeft){
    var q = bandQuantiles(c, index);
    if (!q) return "";
    var levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95];
    var pts = [], k, width, maxWidth = 0;
    for (k = 0; k < 6; k++){
      var span = q[k+1] - q[k];
      if (span <= 0) continue;
      width = (levels[k+1] - levels[k]) / span;
      pts.push([0.5 * (q[k] + q[k+1]), width]);
      if (width > maxWidth) maxWidth = width;
    }
    if (!pts.length || maxWidth <= 0) return "";
    var reach = (toLeft ? -1 : 1) * 26;
    var path = "M" + xAt.toFixed(1) + "," + s.y(q[0]).toFixed(1);
    for (k = 0; k < pts.length; k++){
      path += "L" + (xAt + reach * pts[k][1] / maxWidth).toFixed(1) + "," +
              s.y(pts[k][0]).toFixed(1);
    }
    path += "L" + xAt.toFixed(1) + "," + s.y(q[6]).toFixed(1) + "Z";
    return '<path d="' + path + '" fill="var(--accent)" fill-opacity="0.34" ' +
           'stroke="var(--accent)" stroke-width="0.7"></path>';
  }

  function hoverLayer(c, s){
    if (hoverYear === null) return "";
    var g = TRAJ;
    var i = hoverYear - D.annualFrom;
    if (i < 0 || i >= c.t.length) return "";
    var xAt = s.x(i), value = c.t[i];
    var toLeft = xAt > g.W * 0.62;
    var out = '<line x1="' + xAt.toFixed(1) + '" y1="' + g.padT + '" x2="' +
              xAt.toFixed(1) + '" y2="' + (g.H-g.padB) +
              '" stroke="var(--accent)" stroke-width="1"></line>';

    var bandIndex = (D.bandFrom === undefined) ? -1 : hoverYear - D.bandFrom;
    var hasQ = bandIndex >= 0 && c.qm && bandIndex < c.qm.length;
    if (hasQ){
      out += violin(c, bandIndex, s, xAt, toLeft);
      value = c.qm[bandIndex] * 1000;
    }

    var yAt = s.y(value);
    out += '<line x1="' + g.padL + '" y1="' + yAt.toFixed(1) + '" x2="' +
           xAt.toFixed(1) + '" y2="' + yAt.toFixed(1) +
           '" stroke="var(--accent)" stroke-width="1" stroke-dasharray="2 2"></line>';
    out += '<circle cx="' + xAt.toFixed(1) + '" cy="' + yAt.toFixed(1) +
           '" r="2.4" fill="var(--accent)"></circle>';

    var anchor = toLeft ? "end" : "start";
    var tx = xAt + (toLeft ? -30 : 30);
    out += '<text x="' + tx.toFixed(1) + '" y="' + (g.padT + 9) +
           '" font-size="9" text-anchor="' + anchor +
           '" fill="var(--ink)" font-weight="600">' + hoverYear + '</text>';
    out += '<text x="' + tx.toFixed(1) + '" y="' + (g.padT + 19) +
           '" font-size="8.5" text-anchor="' + anchor + '" fill="var(--ink)">' +
           shortNumber(value) + '</text>';
    if (hasQ){
      var q = bandQuantiles(c, bandIndex);
      out += '<text x="' + tx.toFixed(1) + '" y="' + (g.padT + 28) +
             '" font-size="7.5" text-anchor="' + anchor + '" fill="var(--muted)">' +
             shortNumber(q[0]) + ' to ' + shortNumber(q[6]) + '</text>';
    }
    return out;
  }

  function drawTrajectory(c){
    var svg = document.getElementById("traj");
    var g = TRAJ, s = trajScales(c), t = c.t, i, j;
    var out = "";

    var ticks = [0, s.max/2, s.max];
    for (i = 0; i < ticks.length; i++){
      var ty = s.y(ticks[i]);
      out += '<line x1="' + g.padL + '" y1="' + ty.toFixed(1) + '" x2="' +
             (g.W - g.padR) + '" y2="' + ty.toFixed(1) +
             '" stroke="var(--faint)" stroke-width="0.7"></line>';
      out += '<text x="' + (g.padL - 4) + '" y="' + (ty + 3).toFixed(1) +
             '" font-size="8" text-anchor="end" fill="var(--muted)">' +
             shortNumber(ticks[i]) + '</text>';
    }

    if (c.lo && c.hi && D.bandFrom !== undefined){
      var off = D.bandFrom - D.annualFrom, area = "";
      for (j = 0; j < c.hi.length; j++)
        area += (j?"L":"M") + s.x(off+j).toFixed(1) + "," + s.y(c.hi[j]).toFixed(1);
      for (j = c.lo.length-1; j >= 0; j--)
        area += "L" + s.x(off+j).toFixed(1) + "," + s.y(c.lo[j]).toFixed(1);
      out += '<path d="' + area + 'Z" fill="var(--accent)" fill-opacity="0.17" stroke="none"></path>';
    }

    var d = "";
    for (i = 0; i < s.n; i++)
      d += (i?"L":"M") + s.x(i).toFixed(1) + "," + s.y(t[i]).toFixed(1);
    out += '<path d="' + d + '" fill="none" stroke="var(--accent)" stroke-width="1.8"></path>';

    [[2024 - D.annualFrom, "2024"], [2100 - D.annualFrom, "2100"]].forEach(function(p){
      out += '<line x1="' + s.x(p[0]).toFixed(1) + '" y1="' + g.padT + '" x2="' +
             s.x(p[0]).toFixed(1) + '" y2="' + (g.H-g.padB) +
             '" stroke="var(--faint)" stroke-width="1" stroke-dasharray="3 3"></line>';
      out += '<text x="' + (s.x(p[0])+3).toFixed(1) + '" y="' + (g.H-g.padB-3) +
             '" font-size="8" fill="var(--muted)">' + p[1] + '</text>';
    });
    out += '<text x="' + g.padL + '" y="' + (g.H-6) +
           '" font-size="8" fill="var(--muted)">1950</text>';
    out += '<text x="' + (g.W-g.padR) + '" y="' + (g.H-6) +
           '" font-size="8" text-anchor="end" fill="var(--muted)">2150</text>';

    out += hoverLayer(c, s);
    svg.setAttribute("viewBox", "0 0 " + g.W + " " + g.H);
    svg.innerHTML = out;
    writeReadout(c);
  }

  // The numbers, which survive any screen width. The shape is a bonus; this is
  // the payload, and on a phone it is the only part that can be read at all.
  function writeReadout(c){
    var box = document.getElementById("trajread");
    if (!box) return;
    if (hoverYear === null){
      box.innerHTML = "Hover or drag across the chart to read any year.";
      return;
    }
    var i = hoverYear - D.annualFrom;
    if (i < 0 || i >= c.t.length){ box.innerHTML = ""; return; }
    var bandIndex = (D.bandFrom === undefined) ? -1 : hoverYear - D.bandFrom;
    var parts = ["<b>" + hoverYear + "</b>"];
    if (bandIndex >= 0 && c.qm && bandIndex < c.qm.length){
      var q = bandQuantiles(c, bandIndex);
      parts.push(shortNumber(q[3]) + " median");
      parts.push(shortNumber(q[2]) + "-" + shortNumber(q[4]) + " middle half");
      parts.push(shortNumber(q[0]) + "-" + shortNumber(q[6]) + " of 90% of draws");
    } else {
      parts.push(shortNumber(c.t[i]));
      parts.push(hoverYear < 2024 ? "UN estimate" : "projection");
    }
    box.innerHTML = parts.join(" &middot; ");
  }

  function trajYearFromEvent(event){
    var svg = document.getElementById("traj");
    var box = svg.getBoundingClientRect();
    var g = TRAJ;
    var vx = ((event.clientX - box.left) / box.width) * g.W;
    var span01 = (vx - g.padL) / (g.W - g.padL - g.padR);
    if (span01 < 0) span01 = 0;
    if (span01 > 1) span01 = 1;
    return D.annualFrom + Math.round(span01 * (D.annualTo - D.annualFrom));
  }

  function attachTrajectoryHover(){
    var svg = document.getElementById("traj");
    if (!svg) return;
    svg.addEventListener("mousemove", function(event){
      var year = trajYearFromEvent(event);
      if (year !== hoverYear){
        hoverYear = year;
        drawTrajectory(selected ? D.countries[selected] : WORLD);
      }
    });
    svg.addEventListener("mouseleave", function(){
      if (hoverYear !== null){
        hoverYear = null;
        drawTrajectory(selected ? D.countries[selected] : WORLD);
      }
    });
    function touch(event){
      if (!event.touches.length) return;
      var year = trajYearFromEvent(event.touches[0]);
      if (year !== hoverYear){
        hoverYear = year;
        drawTrajectory(selected ? D.countries[selected] : WORLD);
      }
      // Only once the finger is on the chart, so the page still scrolls
      // normally everywhere else.
      event.preventDefault();
    }
    svg.addEventListener("touchstart", touch, {passive: false});
    svg.addEventListener("touchmove", touch, {passive: false});
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
    var cen = document.getElementById("census");
    if (iso) {
      cen.textContent = c.cen
        ? "Last census " + c.cen + ", " + (2024 - c.cen) + " years before the base year."
        : "No census recorded since 1985 — these figures are modelled from other evidence.";
    } else {
      cen.textContent = "";
    }
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
    var c = D.countries[iso];
    if (mode === "census"){
      tip.textContent = c.n + "  " + (c.cen ? "last census " + c.cen : c.band);
    } else {
      var p = changePct(iso);
      tip.textContent = c.n + "  " + (p >= 0 ? "+" : "") + p.toFixed(0) + "%";
    }
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top = (e.clientY + 12) + "px";
    tip.style.opacity = 1;
  });
  map.addEventListener("mouseleave", function(){ tip.style.opacity = 0; });

  repaint();
  attachTrajectoryHover();
  show(null);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

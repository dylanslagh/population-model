"""Check the built map without opening a browser.

    python scripts/check_map.py

Three things, none of which need a rendering engine:

1. The embedded JSON is parsed back out and its shape checked - every country
   present, every array the length it claims, no country without either a
   polygon or a point.
2. The inline JavaScript is extracted and run through `node --check`, which
   catches syntax errors. A single missing brace would leave a blank page.
3. The choropleth is redrawn in Python, using the same colour stops and the
   same numbers the page uses, and written to out/map-check.png. That is the
   part worth actually looking at: it verifies the colour scale and the
   change-percentage logic, which is where a wrong answer would look plausible.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from popmodel import paths  # noqa: E402

# The map moved to map/index.html when the public site took over the root
# index.html. build_map.py writes here; this must follow it.
PAGE = paths.REPO_ROOT / "map" / "index.html"

# Must stay in step with STOPS in the page.
STOPS = [
    (-100, (122, 42, 17)), (-50, (153, 60, 29)), (-25, (216, 90, 48)),
    (-10, (240, 153, 123)), (0, (211, 209, 199)), (10, (93, 202, 165)),
    (50, (29, 158, 117)), (100, (15, 110, 86)), (400, (4, 52, 44)),
]


def colour(pct):
    if pct is None:
        return "#D3D1C7"
    v = max(-100.0, min(400.0, pct))
    for (a_v, a_c), (b_v, b_c) in zip(STOPS, STOPS[1:]):
        if v <= b_v:
            t = (v - a_v) / (b_v - a_v)
            rgb = [round(a_c[k] + t * (b_c[k] - a_c[k])) for k in range(3)]
            return "#%02x%02x%02x" % tuple(rgb)
    return "#%02x%02x%02x" % STOPS[-1][1]


def parse_path(d: str):
    """Turn an SVG path of M...L...Z subpaths back into point lists."""
    rings = []
    for chunk in d.split("M"):
        if not chunk.strip():
            continue
        chunk = chunk.rstrip("Z")
        pts = []
        for pair in chunk.split("L"):
            if "," not in pair:
                continue
            x, y = pair.split(",")
            pts.append((float(x), float(y)))
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def main() -> int:
    if not PAGE.exists():
        raise SystemExit(f"{PAGE} missing. Run: python scripts/build_map.py")
    html = PAGE.read_text(encoding="utf-8")
    problems = []

    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit("no embedded payload found")
    data = json.loads(m.group(1))
    print(f"1. payload parses: {len(data['countries'])} countries, "
          f"{len(data['shapes'])} shapes, {len(m.group(1)) / 1e6:.1f} MB of JSON")

    n_years = len(data["pyramidYears"])
    n_annual = data["annualTo"] - data["annualFrom"] + 1
    for iso, c in data["countries"].items():
        if len(c["f"]) != n_years or len(c["m"]) != n_years:
            problems.append(f"{iso}: {len(c['f'])} pyramid years, expected {n_years}")
        if any(len(row) != 101 for row in c["f"] + c["m"]):
            problems.append(f"{iso}: a pyramid row is not 101 ages long")
        # A pyramid that sums to nothing while the country has people in it
        # means precision was lost somewhere in the export.
        pyr_2024 = sum(c["f"][data["pyramidYears"].index(2024)]) +             sum(c["m"][data["pyramidYears"].index(2024)])
        live = c["t"][2024 - data["annualFrom"]]
        if live > 0 and pyr_2024 == 0:
            problems.append(f"{iso}: has {live} people but an empty pyramid")
        if live > 0 and abs(pyr_2024 - live) / live > 0.01:
            problems.append(f"{iso}: pyramid sums to {pyr_2024} but total says {live}")
        if len(c["t"]) != n_annual:
            problems.append(f"{iso}: {len(c['t'])} annual values, expected {n_annual}")
        if iso not in data["shapes"] and "pt" not in c:
            problems.append(f"{iso}: neither a shape nor a point - it would be invisible")
    print(f"   every country has {n_years} pyramids of 101 ages and {n_annual} annual totals"
          if not problems else f"   {len(problems)} problem(s)")

    script = re.search(r"<script>\s*\(function\(\)\{(.*?)</script>", html, re.S)
    if not script:
        problems.append("could not find the page script")
    else:
        country_rule = re.search(r"\.country\s*\{([^}]*)\}", html, re.S)
        class_sets_fill = bool(country_rule and
                               re.search(r"(?:^|;)\s*fill\s*:", country_rule.group(1)))
        uses_presentation_fill = 'setAttribute("fill", fillFor(' in script.group(1)
        if class_sets_fill and uses_presentation_fill:
            problems.append(
                "the .country CSS fill overrides the choropleth presentation attribute"
            )
        else:
            print("2. map colours survive the CSS cascade")

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write("(function(){" + script.group(1))
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                print("   javascript passes node --check")
            else:
                problems.append("javascript syntax error:\n" + (r.stderr or r.stdout))
        except FileNotFoundError:
            print("   node not available; skipped the syntax check")
        finally:
            Path(tmp).unlink(missing_ok=True)

    # 3. redraw the choropleth from the page's own numbers
    i2024 = 2024 - data["annualFrom"]
    i2100 = 2100 - data["annualFrom"]
    fig, ax = plt.subplots(figsize=(15, 8), dpi=110)
    for iso, d in data["shapes"].items():
        c = data["countries"][iso]
        pct = (c["t"][i2100] / c["t"][i2024] - 1) * 100 if c["t"][i2024] else None
        for ring in parse_path(d):
            ax.add_patch(MplPolygon(ring, closed=True, facecolor=colour(pct),
                                    edgecolor="white", linewidth=0.3))
    ax.set_xlim(0, data["viewWidth"])
    ax.set_ylim(data["viewHeight"], 0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Projected population change, 2024 to 2100 - redrawn from the page's own data",
                 fontsize=11, loc="left", color="#2C2C2A")
    handles = [plt.Line2D([0], [0], marker="s", linestyle="", markersize=10,
                          markerfacecolor=colour(v), markeredgecolor="none",
                          label=("+" if v > 0 else "") + f"{v}%")
               for v in (-75, -50, -25, 0, 50, 100, 200)]
    ax.legend(handles=handles, loc="lower left", frameon=False, ncol=7, fontsize=9)
    fig.tight_layout()
    out = paths.OUT / "map-check.png"
    fig.savefig(out, format="png", facecolor="white")
    plt.close(fig)
    print(f"3. wrote {out.relative_to(paths.REPO_ROOT)} - open it and look at it")

    # 3b. the same for the data-confidence mode, whose colours are a lookup
    # rather than a ramp and so fail differently: a band name that does not
    # match the table renders as "no data" and looks deliberate.
    bands = [("within 5 years", "#9FE1CB"), ("5 to 14 years", "#FAC775"),
             ("15 years or more", "#D85A30"), ("none since 1985", "#712B13"),
             ("not listed", "#B4B2A9")]
    band_colour = dict(bands)
    unknown = sorted({c.get("band") for c in data["countries"].values()} - set(band_colour))
    if unknown:
        problems.append(f"band values with no colour: {unknown}")
    fig, ax = plt.subplots(figsize=(15, 8), dpi=110)
    for iso, d in data["shapes"].items():
        col = band_colour.get(data["countries"][iso].get("band"), "#EEEEEE")
        for ring in parse_path(d):
            ax.add_patch(MplPolygon(ring, closed=True, facecolor=col,
                                    edgecolor="white", linewidth=0.3))
    ax.set_xlim(0, data["viewWidth"]); ax.set_ylim(data["viewHeight"], 0)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("How long since each country ran a census - redrawn from the page's own data",
                 fontsize=11, loc="left", color="#2C2C2A")
    ax.legend(handles=[plt.Line2D([0], [0], marker="s", linestyle="", markersize=10,
                                  markerfacecolor=c, markeredgecolor="none", label=n)
                       for n, c in bands],
              loc="lower left", frameon=False, ncol=5, fontsize=9)
    fig.tight_layout()
    out2 = paths.OUT / "map-check-census.png"
    fig.savefig(out2, format="png", facecolor="white")
    plt.close(fig)
    print(f"   wrote {out2.relative_to(paths.REPO_ROOT)}")

    interesting = ["NGA", "COD", "IND", "CHN", "JPN", "KOR", "USA", "DEU", "NER"]
    print("\n   change 2024 to 2100, as the page computes it:")
    for iso in interesting:
        c = data["countries"].get(iso)
        if not c:
            continue
        pct = (c["t"][i2100] / c["t"][i2024] - 1) * 100
        print(f"     {iso}  {c['t'][i2024]/1e6:>9,.1f}m -> {c['t'][i2100]/1e6:>9,.1f}m  "
              f"{pct:>+7.0f}%")

    # 4. The uncertainty band, checked the same way as everything else: parsed
    # back out of the page and redrawn from the page's own numbers.
    if "bandFrom" in data:
        band_years = list(range(data["bandFrom"], data["annualTo"] + 1))
        with_band = [iso for iso, c in data["countries"].items() if "lo" in c]
        print(f"\n4. uncertainty band on {len(with_band)} of "
              f"{len(data['countries'])} countries, "
              f"{band_years[0]}-{band_years[-1]}")
        inside = 0
        for iso in with_band:
            c = data["countries"][iso]
            if len(c["lo"]) != len(band_years) or len(c["hi"]) != len(band_years):
                problems.append(f"{iso}: band is {len(c['lo'])} years, "
                                f"expected {len(band_years)}")
                continue
            if any(lo > hi for lo, hi in zip(c["lo"], c["hi"])):
                problems.append(f"{iso}: the 5th percentile exceeds the 95th")
            if any(v < 0 for v in c["lo"]):
                problems.append(f"{iso}: the band goes below zero people")
            k = 2100 - data["bandFrom"]
            if c["lo"][k] <= c["t"][i2100] <= c["hi"][k]:
                inside += 1
        share = inside / max(len(with_band), 1)
        print(f"   the deterministic 2100 line sits inside the band for "
              f"{share:.0%} of countries")
        # The line is a different run from the band - the UN's own assumptions
        # with residual migration - so it is not obliged to sit inside. A low
        # share would mean the two runs disagree about something structural,
        # which is worth stopping for.
        if share < 0.5:
            problems.append(
                f"only {share:.0%} of deterministic 2100 values fall inside the "
                f"ensemble band; the two runs disagree structurally"
            )
        if "worldBand" not in data:
            problems.append("countries carry a band but the world does not")
        else:
            lo, hi = data["worldBand"]
            if any(a > b for a, b in zip(lo, hi)):
                problems.append("the world band's 5th percentile exceeds its 95th")
            country_lo = sum(data["countries"][i]["lo"][-1] for i in with_band)
            print(f"   world 2150 band {lo[-1]/1e9:.2f}-{hi[-1]/1e9:.2f}bn; "
                  f"summing country 5th percentiles would say "
                  f"{country_lo/1e9:.2f}bn, which is why it is not done that way")

        # The hover reads seven percentiles per country per year. They are
        # stored as a median plus six ratios, which is compact and easy to get
        # subtly wrong, so they are checked here in the form the page uses.
        quantile_countries = [iso for iso in with_band if "qm" in data["countries"][iso]]
        print(f"   per-year distribution stored for {len(quantile_countries)} countries")
        for iso in quantile_countries:
            c = data["countries"][iso]
            if len(c["qm"]) != len(band_years):
                problems.append(f"{iso}: median series is the wrong length")
                continue
            if len(c["qr"]) != 6:
                problems.append(f"{iso}: expected six ratio series, got {len(c['qr'])}")
                continue
            if any(len(series) != len(band_years) for series in c["qr"]):
                problems.append(f"{iso}: a ratio series is the wrong length")
                continue
            for k in range(0, len(band_years), 17):
                median = c["qm"][k] * 1000
                levels = [c["qr"][j][k] * median / 10000 for j in range(6)]
                ordered = levels[:3] + [median] + levels[3:]
                if any(b < a - 1 for a, b in zip(ordered, ordered[1:])):
                    problems.append(f"{iso}: percentiles are out of order at {band_years[k]}")
                    break
                # The 5th and 95th here must agree with the band drawn behind
                # the line, or the hover and the shading tell different stories.
                if abs(ordered[0] - c["lo"][k]) > max(1000.0, 0.02 * abs(c["lo"][k])):
                    problems.append(
                        f"{iso}: the hover's 5th percentile disagrees with the band "
                        f"at {band_years[k]}"
                    )
                    break
                if abs(ordered[-1] - c["hi"][k]) > max(1000.0, 0.02 * abs(c["hi"][k])):
                    problems.append(
                        f"{iso}: the hover's 95th percentile disagrees with the band "
                        f"at {band_years[k]}"
                    )
                    break

        sample = data["countries"].get("USA")
        if sample and "qm" in sample:
            k = 2100 - data["bandFrom"]
            median = sample["qm"][k] * 1000
            spread = [sample["qr"][j][k] / 10000 for j in range(6)]
            print(
                f"   USA 2100: median {median/1e6:.0f}m, percentile ratios "
                + ", ".join(f"{r:.2f}" for r in spread)
            )


        # Run the page's own chart code, with the page's own data, and confirm
        # it draws something rather than "MNaN,NaN". node --check proves the
        # script parses; it does not prove that hovering 2087 over Tuvalu works.
        hover_js = paths.REPO_ROOT / "scripts" / "check_hover.js"
        if hover_js.exists():
            result = subprocess.run(
                ["node", str(hover_js), str(PAGE)],
                capture_output=True, text=True,
            )
            for line in result.stdout.strip().splitlines():
                print("   " + line.strip())
            if result.returncode != 0:
                problems.append("the hover rendering check failed")

        # And draw it, because a shape that is technically valid can still be
        # the wrong shape, and nothing here opens a browser.
        fig, hov = plt.subplots(1, 2, figsize=(9.6, 3.8))
        for panel, (iso, year) in zip(hov, (("USA", 2100), ("NGA", 2150))):
            c = data["countries"].get(iso)
            if not c or "qm" not in c:
                continue
            k = min(year - data["bandFrom"], len(c["qm"]) - 1)
            median = c["qm"][k] * 1000
            col = [c["qr"][j][k] * median / 10000 for j in range(6)]
            levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
            values = col[:3] + [median] + col[3:]
            panel.fill_between(band_years, [v / 1e6 for v in c["lo"]],
                               [v / 1e6 for v in c["hi"]], color="#4575b4",
                               alpha=0.18, lw=0)
            panel.plot(range(data["annualFrom"], data["annualTo"] + 1),
                       [v / 1e6 for v in c["t"]], color="#4575b4", lw=1.6)
            # The density the page draws: probability per unit width.
            widths, mids = [], []
            for j in range(6):
                span = values[j + 1] - values[j]
                if span <= 0:
                    continue
                widths.append((levels[j + 1] - levels[j]) / span)
                mids.append(0.5 * (values[j] + values[j + 1]) / 1e6)
            if widths:
                # The page flips the shape to the left of the guide once the
                # year is past about three fifths of the chart, so it never
                # runs off the edge. The redraw has to do the same or it is not
                # checking what the page does.
                span = data["annualTo"] - data["annualFrom"]
                to_left = (year - data["annualFrom"]) / span > 0.62
                scale = (-18.0 if to_left else 18.0) / max(widths)
                panel.plot([year] + [year + w * scale for w in widths] + [year],
                           [values[0] / 1e6] + mids + [values[-1] / 1e6],
                           color="#4575b4", lw=1.0)
                panel.fill([year] + [year + w * scale for w in widths] + [year],
                           [values[0] / 1e6] + mids + [values[-1] / 1e6],
                           color="#4575b4", alpha=0.34)
            panel.axvline(year, color="#4575b4", lw=1)
            panel.axhline(median / 1e6, color="#4575b4", lw=1, ls=(0, (2, 2)))
            panel.set_xlim(1950, data["annualTo"])
            panel.set_ylim(bottom=0)
            panel.set_title(f"{iso}, hovering {year}", fontsize=10)
            panel.set_ylabel("millions")
            panel.spines[["top", "right"]].set_visible(False)
        fig.suptitle("The hover, redrawn in Python from the page's own numbers",
                     fontsize=10.5)
        fig.tight_layout()
        out4 = paths.OUT / "map-check-hover.png"
        fig.savefig(out4, dpi=140)
        plt.close(fig)
        print(f"   wrote {out4.relative_to(paths.REPO_ROOT)} - open it and look at it")

        fig, ax = plt.subplots(figsize=(7.6, 4.2))
        for iso, line_colour in (("USA", "#4575b4"), ("NGA", "#1a9850"), ("JPN", "#d73027")):
            c = data["countries"].get(iso)
            if not c or "lo" not in c:
                continue
            ax.fill_between(band_years, [v / 1e6 for v in c["lo"]],
                            [v / 1e6 for v in c["hi"]], color=line_colour, alpha=0.18, lw=0)
            ax.plot(range(data["annualFrom"], data["annualTo"] + 1),
                    [v / 1e6 for v in c["t"]], color=line_colour, lw=1.6, label=iso)
        ax.set_xlim(1950, data["annualTo"])
        ax.set_ylim(bottom=0)
        ax.set_xlabel("year")
        ax.set_ylabel("population, millions")
        ax.set_title("Redrawn from the page's own numbers: line and band", fontsize=10)
        ax.legend(fontsize=8, frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        out3 = paths.OUT / "map-check-band.png"
        fig.savefig(out3, dpi=140)
        plt.close(fig)
        print(f"   wrote {out3.relative_to(paths.REPO_ROOT)} - open it and look at it")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  " + p)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

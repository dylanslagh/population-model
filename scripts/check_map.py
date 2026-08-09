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

PAGE = paths.REPO_ROOT / "index.html"

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
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write("(function(){" + script.group(1))
            tmp = fh.name
        try:
            r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                print("2. javascript passes node --check")
            else:
                problems.append("javascript syntax error:\n" + (r.stderr or r.stdout))
        except FileNotFoundError:
            print("2. node not available; skipped the syntax check")
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

    interesting = ["NGA", "COD", "IND", "CHN", "JPN", "KOR", "USA", "DEU", "NER"]
    print("\n   change 2024 to 2100, as the page computes it:")
    for iso in interesting:
        c = data["countries"].get(iso)
        if not c:
            continue
        pct = (c["t"][i2100] / c["t"][i2024] - 1) * 100
        print(f"     {iso}  {c['t'][i2024]/1e6:>9,.1f}m -> {c['t'][i2100]/1e6:>9,.1f}m  "
              f"{pct:>+7.0f}%")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  " + p)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

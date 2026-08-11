// Execute the page's own trajectory-drawing code against the page's own data.
// node --check proves the script parses; it does not prove that hovering 2087
// over Tuvalu produces a path instead of "MNaN,NaN". This does.
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");

const payload = JSON.parse(
  html.match(/<script id="payload" type="application\/json">([\s\S]*?)<\/script>/)[1]
);

const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const start = script.indexOf("var TRAJ = {");
const end = script.indexOf("function trajYearFromEvent");
if (start < 0 || end < 0) { console.error("could not find the chart code"); process.exit(1); }
const chartCode = script.slice(start, end);

// One stub element per id. Sharing one meant the readout text overwrote the
// captured SVG, and the check reported "no path drawn" for a page that draws
// one perfectly well.
const elements = {};
const captured = {get svg(){ return (elements.traj || {}).html || ""; }};
const document = {
  getElementById: (id) => {
    if (!elements[id]) elements[id] = {
      html: "",
      setAttribute: () => {},
      set innerHTML(v){ this.html = v; },
      get innerHTML(){ return this.html; },
    };
    return elements[id];
  },
};
const D = payload;
let hoverYear = null;

const run = new Function("document", "D", "hoverYearRef", chartCode + `
  return {
    draw: function(c, year){ hoverYear = year; drawTrajectory(c); },
    quantiles: bandQuantiles,
  };
`);
const api = run(document, D, null);

let checked = 0, problems = [];
const isos = Object.keys(D.countries);
const sample = ["USA", "NGA", "TUV", "ISR", "JPN", "VAT"].filter(i => D.countries[i])
  .concat(isos.slice(0, 40));

for (const iso of new Set(sample)) {
  const c = D.countries[iso];
  for (const year of [null, 1950, 1975, 2024, 2087, 2100, 2149, 2150]) {
    api.draw(c, year);
    const svg = captured.svg;
    if (/NaN|Infinity|undefined/.test(svg)) {
      problems.push(`${iso} at ${year}: output contains NaN/Infinity/undefined`);
      break;
    }
    if (!svg.includes("<path")) { problems.push(`${iso} at ${year}: no path drawn`); break; }
    // A distribution is only drawable where the draws actually disagree. At
    // the base year they all start from the same population, so zero width and
    // nothing drawn is the correct answer, not a missing feature.
    if (year !== null && c.qm && D.bandFrom !== undefined) {
      const k = year - D.bandFrom;
      if (k >= 0 && k < c.qm.length) {
        const col = api.quantiles(c, k);
        const spread = col[6] - col[0];
        const drawn = svg.includes('fill-opacity="0.34"');
        if (spread > 1 && !drawn) {
          problems.push(`${iso} at ${year}: draws differ by ${Math.round(spread)} but no distribution drawn`);
          break;
        }
        if (spread === 0 && drawn) {
          problems.push(`${iso} at ${year}: drew a distribution where every draw agrees`);
          break;
        }
      }
    }
    checked++;
  }
}

// The hover's median must equal the stored median, not the deterministic line.
const usa = D.countries["USA"];
const k = 2100 - D.bandFrom;
const q = api.quantiles(usa, k);
if (!(q[0] < q[3] && q[3] < q[6])) problems.push("USA 2100 percentiles are out of order");
const spread = ((q[6] - q[0]) / q[3] * 100).toFixed(0);

console.log(`  rendered ${checked} country/year combinations without a NaN`);
console.log(`  USA 2100 from the page's own data: median ${(q[3]/1e6).toFixed(0)}m, `
  + `90% range ${(q[0]/1e6).toFixed(0)}-${(q[6]/1e6).toFixed(0)}m (${spread}% of the median)`);
if (problems.length) {
  console.log("PROBLEMS:");
  for (const p of problems.slice(0, 8)) console.log("  " + p);
  process.exit(1);
}
console.log("  hover rendering OK");

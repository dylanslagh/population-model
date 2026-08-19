# The public site

`population.dylanslagh.com`. One page that tells the argument while a rotating
Earth, lit by the model's own population, runs behind it.

## What is in here

| | |
|---|---|
| `index.template.html` | the shell: head, meta, and all the CSS |
| `body.html` | every word on the page, and the scroll choreography as `data-stage` |
| `app.js` | the globe, the scroll driver, and the figures |
| `data/globe.json` | country outlines and one light per million people |
| `data/story.json` | every number the page quotes, copied from the result files |
| `social-card.jpg` | the 1200x630 link preview |

`scripts/build_site.py` assembles these into `index.html` at the repository
root. Nothing here is served directly; `index.html` is the artifact, and
`scripts/build_public.py` stages it.

## Building it

```bash
python scripts/build_site_assets.py   # only when the model or the outlines move
python scripts/build_site.py          # after any edit in this folder
```

`build_site_assets.py` is standard-library only and needs two things a fresh
clone may not have: the Natural Earth outlines (`python scripts/fetch_geometry.py`,
6 MB, checksum-verified) and the built map page, which carries the per-country
population series in its payload. It does **not** need the 1.1 GB of WPP source
data, which is the point: the site can be rebuilt on any machine.

## The rule that matters

Any element on the page carrying `data-v="some.path"` names a value in
`data/story.json`, and `build_site.py` fails if the text inside it disagrees.
So the prose cannot quietly drift away from the model:

```html
<b class="v" data-v="boundary.rate" data-dp="2">1.52%</b>
```

Rounding is allowed (`8.78` may be printed as `8.8`); restating is not. Add
`data-dp` to fix the decimal places, `data-fmt="millions"` to divide by a
million first. `tests/test_site.py` runs the same check against the committed
page, so a stale number fails the test suite as well as the build.

## Things the page is careful about

* **The globe stops at 2100**, where the UN's published assumptions stop.
  Nothing on it is this project extrapolating.
* **The lights are not cities.** Each is a million people scattered at random
  inside its own country, because the model is country-level. The page says so
  where a reader can see it.
* **Three labels stay separate**: the UN reproduction to 2100, this project's
  extension past it, and the selection model that forks in 2024. They are
  different runs and the page never merges them into one line.
* **Colours are validated, not chosen by eye.** The categorical set and the
  sequential ramp both pass a colour-vision, chroma and contrast check against
  this page's near-black surface. Do not substitute a hex by taste.
* **Every figure has a table** under "Show the numbers", so nothing is
  available only as a picture.

## Rendering the social card

The card is a screenshot of the page's own hero, taken at 1200x630 in headless
Chromium and saved as JPEG at quality 88. There is no script for it in the repo
because it is a once-a-redesign job and Playwright is not a dependency of
anything else here.

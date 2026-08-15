# Publishing the race video

Copy-ready title, description, thumbnail and music notes for
`out/race-1950-2100.mp4`. Rendered by `scripts/render_race.py`; thumbnails by
`scripts/render_thumbnail.py`.

The video is **1:46** (106 s), 1920x1080, 30 fps, no audio track.

## Title

Recommended, 58 characters, keywords first:

> The 12 Biggest Countries, 1950–2100 — With the Uncertainty

Alternatives:

> Every Population Race Video Hides This (1950–2100)
> 150 Years of World Population: 1950 to 2100, UN Data
> What the UN Actually Knows About 2100

The first is the honest one and still has a hook. The second is the highest
click-rate phrasing and is defensible — it is true that the genre draws single
confident lines — but it picks a fight, and this project's whole posture is that
it would rather show its own ignorance than somebody else's error.

## Description

Everything above the fold is the first three lines. The source attribution is
not optional: the video's legitimacy rests on it.

```
The twelve most populous countries from 1950 to 2100, using the UN's own
figures — and, from 2024, showing how much the projection actually disagrees
with itself.

Watch 0:51. That is where the UN's estimates of the past stop and the
projection begins, and a whisker appears on every bar. It keeps widening for
the rest of the video. That range is the part every other population race
video leaves out.

WHERE THE NUMBERS COME FROM
• The bars are the UN World Population Prospects 2024. Through 2023 they are
  the UN's reconstruction of what already happened; from 2024 they are its
  medium projection.
• The whiskers are the 5th to 95th percentile of 1,000 draws from the
  University of Washington's Bayesian population posterior — a separate
  publication from the UN's medium variant, though the UN's own probabilistic
  work uses that group's method.
• It stops at 2100 because that is where the UN's published assumptions stop.
  Anything past 2100 would be my own extrapolation, and it does not belong in
  a video whose credibility comes from the source.

Sources:
UN World Population Prospects 2024 — https://population.un.org/wpp/
University of Washington / bayesPop posterior — https://bayespop.csss.washington.edu/

Made with a cohort-component projection engine I wrote, which reproduces the
UN's own zero-migration variant at 2100 to within 0.001% at the world level.

Music: [TRACK] by [ARTIST] — [LICENCE / LINK]
```

Replace the music line with whatever the library gives you, or delete it if you
use a track that needs no attribution.

**Timestamps**, if you want chapters. YouTube needs at least three, the first
at 0:00, each at least ten seconds. Derived from the render settings
(1.5 s opening hold, then 1.5 years per second), so they move if those change.

```
0:00 1950
0:35 2000
0:51 the projection begins, and the uncertainty appears
1:08 2050
1:41 2100
```

## Tags

population, demographics, world population, bar chart race, data
visualization, united nations, population projection, 2100, uncertainty,
data science, forecasting

## Thumbnail

`python scripts/render_thumbnail.py` writes three to `out/thumbnails/`. All are
1280x720 and well under YouTube's 2 MB limit. They are the video's own first
frame with the chart squeezed left, so the thumbnail cannot drift away from the
video it advertises.

| Variant | Headline | When to use it |
|---|---|---|
| `takeover` | 1950 → 2100 | Safest. Says exactly what the video is. |
| `uncertainty` | NOBODY KNOWS 2100 | Strongest hook, and honest to the content. |
| `plain` | 150 YEARS OF WORLD POPULATION | Most sober; weakest at small size. |

The headline font size is fitted to the column width rather than hard-coded,
and the script refuses to write a file whose headline runs past the canvas
edge — a cropped word is invisible in a log and obvious to a viewer.

## Music

The video has no audio. It wants roughly 1:50 of something at 70–85 BPM,
instrumental, with no build or drop — the chart is doing the moving, and music
with structure will fight it.

**Where to get it, safest first.**

1. **YouTube Audio Library**, inside YouTube Studio. Cleared specifically for
   YouTube monetisation, so it cannot generate a Content ID claim against your
   own video. Most tracks need no attribution; the subset marked `CC BY` gives
   you the exact credit line to paste. This is the one to use unless you have a
   reason not to.
2. **Pixabay Music.** Free for commercial use, no attribution required.
3. **Uppbeat.** Good lofi catalogue; the free tier requires a credit line and a
   per-track code in the description.
4. **Bensound**, **Free Music Archive**, **Chosic.** Real music under Creative
   Commons, but read each track's licence — CC BY-NC would forbid a monetised
   upload, and CC BY still requires the credit.

**Search terms that land on the right sound:** `lofi`, `lo-fi hip hop`,
`chillhop`, `study beats`, `mellow`, `downtempo`. In the YouTube Audio Library
the genre filter is *Hip Hop & Rap* with mood *Calm*, which is where the
study-beats material actually sits.

**The one trap.** Do not take music from a YouTube channel called "no copyright
music" or similar. Those channels frequently re-upload material they do not own,
and the claim lands on your video, not theirs. Use a library that licenses to
you directly.

I have not verified any individual track — libraries rotate their catalogues,
and a track name I gave you from memory could easily be gone or relicensed. The
libraries above are stable; pick from inside them.

# Publishing the race video

Copy-ready title, description, thumbnail and music notes.

| | |
|---|---|
| Silent master | `out/race-1950-2100.mp4` — `scripts/render_race.py` |
| **Upload this one** | `out/race-1950-2100-music.mp4` — `scripts/add_music.py` |
| Thumbnails | `out/thumbnails/thumbnail-*.png` — `scripts/render_thumbnail.py` |

1:46 (105.5 s), 1920x1080, 30 fps, AAC stereo at 48 kHz.

## Title

Dylan's, chosen 2026-08-15:

> Biggest Countries by Population - Timelapse (2024 UN Estimates - With Uncertainty)

82 characters, inside YouTube's 100. Mobile search truncates around 60, and
this one survives it: "Biggest Countries by Population - Timelapse" is the
first 43 characters and still says what the video is.

## Description

Written as prose rather than the bulleted version that was here first. The
source attribution is the one part that is not stylistic — the video's
legitimacy rests on being exact about whose numbers are whose.

```
Twelve countries, 1950 to 2100, ranked by population every year.

Through 2023 these are the UN's own figures for what already happened. At 0:51
the video crosses into 2024, and a whisker appears on every bar. That is the
range the projection actually covers, and it keeps widening for the rest of
the video. Most population timelapses draw a single confident line all the way
to 2100 and never show it.

The bars are the UN's World Population Prospects, 2024 revision. The whiskers
are the 5th to 95th percentile of 1,000 draws from the University of
Washington's Bayesian posterior — a separate publication, though the UN's own
probabilistic work uses that group's method.

It stops at 2100 because that is where the UN's published assumptions stop.
Anything past that would be my own extrapolation, and it does not belong in a
video that borrows its credibility from the source.

UN World Population Prospects 2024: https://population.un.org/wpp/
University of Washington, bayesPop: https://bayespop.csss.washington.edu/

Music: Cocktail Lounge by Dyalla
```

**On "sounding like AI".** YouTube does not run AI-text detection on
descriptions, and there is no ranking penalty for how a description is phrased.
The disclosure rule that does exist covers realistic synthetic media — a
person or event that could be mistaken for real footage — and a bar chart is
not that. So nothing here is a policy risk. The reason to prefer the prose
version is only that the bulleted one *read* like a template to a human, and
this is a channel where the writing is part of the credibility.

**Timestamps**, if you want chapters. Derived from the render settings (1.5 s
opening hold, then 1.5 years per second) and checked against the encoded file.

```
0:00 1950
0:35 2000
0:51 the projection begins, and the uncertainty appears
1:08 2050
1:41 2100
```

## Tags

population, demographics, world population, bar chart race, timelapse, data
visualization, united nations, population projection, 2100, uncertainty

## Music

`Cocktail Lounge` by Dyalla, chosen 2026-08-15. `scripts/add_music.py` lays it
under the silent master and writes a new file, so swapping the track never
means re-rendering three thousand frames. The video stream is copied rather
than re-encoded.

- Fades in over 1 s, fades out over the last 4 s, so it settles as 2100 lands.
- Normalised to -14 LUFS, which is where YouTube normalises to; the finished
  file measures -13.2, close enough that YouTube will not move it audibly.
- The script refuses to run if the track is shorter than the video, because
  `-shortest` would otherwise truncate the *video* and that looks like a bug
  rather than a choice.

**One thing to check before publishing.** Dyalla's catalogue is distributed in
two ways: free tracks that ask for credit, and tracks licensed through Epidemic
Sound, which are only cleared while you hold a subscription. The downloaded
file carries no licence metadata — its only tag is `encoder=Google`, which is
consistent with the YouTube Audio Library. Use the credit line from wherever
you actually downloaded it. Leaving `Music: Cocktail Lounge by Dyalla` in the
description costs nothing and covers the attribution case either way.

If a track ever needs replacing, the safe libraries are the YouTube Audio
Library (cleared for YouTube monetisation, so it cannot claim your own video),
Pixabay Music (no attribution), and Uppbeat (free tier wants a credit code).
Avoid channels calling themselves "no copyright music" — they frequently
re-upload material they do not own, and the claim lands on you.

## Thumbnail

Three 1280x720 variants, all far under YouTube's 2 MB limit, built from the
video's own first frame so they cannot drift from what they advertise.

| Variant | Headline | Notes |
|---|---|---|
| `takeover` | 1950 → 2100 | Safest. Says exactly what the video is. |
| `uncertainty` | NOBODY KNOWS 2100 | Strongest hook, honest to the content. |
| `plain` | 150 YEARS OF WORLD POPULATION | Soberest, weakest at small size. |

### A/B testing them

**Test & Compare requires YouTube Partner Program membership** — 1,000
subscribers and 4,000 watch hours (or 10 million Shorts views), with advanced
features enabled. It runs in YouTube Studio on desktop only, takes up to two
weeks, and picks the winner on watch time rather than click-through. Three
variants is exactly the maximum, so the set above fits if the channel is
eligible.

If it is not eligible yet, the fallback is manual and still informative:
publish with one thumbnail, leave it a week, swap to another, and compare
impressions click-through rate in Analytics for comparable periods. It is
noisier than a real A/B test because the audience and the video's age are not
held constant, so treat a small difference as nothing.

Worth knowing before spending two weeks on it: all three variants share the
same chart and differ only in the headline. That isolates the text cleanly,
which is a good experiment, but it caps how much the result can move — a test
between genuinely different images usually separates faster.

## Before you can publish

- **Custom thumbnails need verified advanced features.** That is the same
  verification currently in review. Until it clears, YouTube will not accept an
  uploaded thumbnail and will only offer the three auto-generated frames.
- Upload it as **private or unlisted** now if you want it staged, then set the
  thumbnail and flip it to public once verification comes back. Nothing about
  the file changes.
- The two source URLs are plain links in the description. They are the video's
  attribution, so they should not be dropped if links are restricted — a
  non-clickable URL still says where the numbers came from.

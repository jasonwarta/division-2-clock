# Division 2 Clock

A real-time clock that converts wall-clock time to The Division 2's in-game time.

The Division 2's day/night cycle runs ~72 minutes of real time, but in-game hours are not equal length. Dawn and dusk transitions take longer than the dead of night. This page uses hour-by-hour timings collected by hand from captured footage.

## Live

Hosted on GitHub Pages: https://jasonwarta.github.io/division-2-clock/

## How it works

There is no server. The page stores a single anchor timestamp in `localStorage` representing the real-world moment when in-game time was 00:00. On every tick it computes the current in-game time by:

1. Taking elapsed real seconds since the anchor, modulo the 4319-second cycle.
2. Walking the hour-duration table to find which in-game hour we're inside.
3. Linearly interpolating minutes and seconds within that hour.

Click "Sync to 00:00 now" the moment you see in-game midnight, or use the custom sync to enter any in-game time you can read on screen.

## Source data

Timed by a community contributor and posted at:
https://www.reddit.com/r/thedivision/comments/o0a3x0/the_craziness_that_is_division_2s_ingame_hours/

The spreadsheet contained three timing runs. The third (timed against captured footage with an on-screen stopwatch) is used as the source of truth.

## Local dev

No build step. Open `index.html` in a browser, or:

```
npx serve .
```

## Deploying to GitHub Pages

1. Push to GitHub.
2. Repo Settings -> Pages -> Source: "Deploy from a branch", branch `main`, folder `/ (root)`.
3. Wait for the green checkmark and visit the URL.

The `.nojekyll` file disables Jekyll processing so files starting with `_` (none here, but future-proofing) ship as-is.

# Division 2 Clock — Project Notes

A snapshot of where this project stands and how it got here, so we can pick it up later.

## What this is

A static GitHub Pages site that converts wall-clock UTC time to The Division 2's in-game time of day. The page auto-syncs without user input — open it and it just shows the right time.

- **Live URL:** https://jasonwarta.github.io/division-2-clock/
- **Repo:** https://github.com/jasonwarta/division-2-clock
- **Deploy:** GH Pages from `main` branch, root path. No build step.

## How D2's clock works (working hypothesis)

D2's day/night cycle is anchored to wall-clock UTC time as a deterministic function — almost certainly because the open world is sharded and all instances must show the same in-game time. We confirmed this empirically:

- Cycle length: **4322.349 seconds (~72 minutes)**, derived from a 2.5-hour OCR session covering ~2 full cycles.
- 20 cycles per UTC day is *almost* exact (`86400 / 4322.349 ≈ 19.99`), but not quite, so the cycle drifts ~5 seconds per UTC day relative to midnight.
- Cycle origin (anchor): empirically `2026-04-30T17:59:51Z` (the moment in-game = `00:00:00`). All later cycle starts are anchor + N*4322.349s.
- **Hours are not equal length.** Dawn (~hour 8) and dusk (~hour 17) are slowest (~5.4s/in-game-min); midnight (~hour 22) is fastest (~1.8s/in-game-min). The ratio is ~3x.

## Architecture

### Page (static, no build)

- `index.html` — single-page layout: big clock display, scrolling timeline of upcoming hours.
- `style.css` — Tarkov-clock-inspired dark theme. Smooth scrolling timeline with top/bottom gradient fades, fixed orange marker at the "now" line.
- `script.js` — all the logic. Key constants:
  - `MINUTE_DURATIONS_MS` — 1440-element array, real ms per in-game minute (one slot interpolated, rest measured).
  - `CYCLE_MS` — sum of the array, 4322349 ms.
  - `START_CUM_MS` — 1441-element cumulative array; lookup by minute-of-day.
  - `ANCHOR_MS` — Unix ms at the moment in-game was 00:00:00.
- `realToIngame(elapsedMs)` walks `MINUTE_DURATIONS_MS` linearly to find the current minute, then interpolates within it for seconds. Linear walk is fine — 1440 ops per tick is microseconds.

### Data pipeline (Python, in `tools/`)

```
recording.mp4
   |
   | python tools/ocr_clock.py recording.mp4 --bbox X,Y,W,H -o minutes.csv
   v
minutes.csv  (one row per detected minute transition: video_ms, ingame_HH:MM)
   |
   | digit-edit fixer (inline scripts; not yet a tool)
   v
minutes_clean.csv
   |
   | python tools/build_durations.py minutes_clean.csv --anchor-time '...' > new_arrays.js
   v
new_arrays.js  (HOUR_DURATIONS or MINUTE_DURATIONS + DEFAULT_ANCHOR_MS)
```

### Tools

- `tools/ocr_clock.py` — reads a screen recording, OCRs the in-game clock area frame-by-frame, emits a CSV of detected minute transitions. Uses Tesseract (Win install via `winget install UB-Mannheim.TesseractOCR`). Auto-detects recording start time from filename (Win11 Snipping Tool format `YYYYMMDD-HHMM-SS.SSSSSSS.mp4`) or `mtime - duration` fallback. Embeds it as a `# anchor_time=...` header in the CSV.
- `tools/build_durations.py` — ingests `minutes.csv`, computes per-hour or per-minute average durations from clean minute-transition pairs (rejects rows next to gaps), emits paste-ready JS. Pulls anchor_time from CSV header automatically.
- `fit_models.py` — sandbox script for trying parametric fits to the per-minute data. Spoiler: nothing beats the raw 1440-element array.

## How we got here (calibration journey)

### Source data evolution

1. **2021 Reddit dataset** (`https://www.reddit.com/r/thedivision/comments/o0a3x0/`) — 24 hand-timed values, ±2-3s per hour. Used as initial baseline. Cycle: 4319s.
2. **2026-04-30 OCR session** — 2.5hr screen recording of in-game clock with inventory open, 30fps, 270k frames. With OCR errors corrected, gave us 1439 of 1440 minute slots directly measured. Cycle: 4322.349s. Replaced the 2021 data.

### Anchor calibration

We bounced through a few hypotheses:
- **First guess:** midnight UTC = in-game 00:00. Off by ~6 minutes. Approximately right but not exact.
- **OCR-derived from row[1] of CSV:** anchor = recording_start + first_clean_transition_ms - position_in_cycle(HH, MM). Got us within seconds, not minutes.
- **User observation calibration** (page was 4 in-game min behind game at hour 18 → shift anchor 19.6s earlier). Final anchor: `1777571991115`.

The cycle does **not** align exactly to UTC midnight; it's offset by ~7 seconds. This offset compounds to ~5 sec of drift per UTC day relative to midnight, but stays constant relative to the cycle origin.

### OCR error patterns (and fixes)

Tesseract on a small (66×35 → 80×35 wide) clock crop at 4x upscale had several systematic failure modes. We characterized and fixed each:

| Pattern | Cause | Fix |
|---|---|---|
| `1X:YY` → `0X:YY` (leading 1 dropped) | Tesseract loses leading "1" | Edit-distance-1 fixer |
| `06:YY` → `00:YY` (6 looks like 0) | Glyph similarity | Edit-distance-1 fixer |
| `MM:X9` → `MM:X3` (9 misread as 3) | Glyph similarity | Edit-distance-1 fixer |
| `MM:X8` → `MM:X3` (8 misread as 3) | Glyph similarity | Edit-distance-1 fixer |
| Minutes ending in 6 or 9 *missed entirely* | Pixel diff between e.g. "5" and "6" too small to trigger OCR | Lowered `--diff-threshold` from 5.0 to 1.0 |

The fixer logic is currently inline Python scripts (in our chat history); should be hoisted into a proper `tools/fix_ocr.py` if we re-run.

### Architecture decisions worth remembering

- **Track durations in ms, not seconds.** OCR has ~33ms (1-frame at 30fps) precision; rounding to seconds loses ~14% of that.
- **Per-minute beat per-hour.** With 1439/1440 coverage, the array goes from 24 to 1440 entries but eliminates the within-hour averaging error. ~5 KB cost, much smoother time advancement.
- **No parametric formula fits.** We tried 1-5 harmonic Fourier, two Gaussians, two raised-cos bumps, sun-altitude `cos^p`. Best was 5-harmonic Fourier at 265ms RMS error. The data has a noise floor of ~137ms (OCR jitter) that no smooth model can break through. The dominant 12-hour harmonic captures only 53% of variance.
- **Dropped manual sync UI.** Once we had `ANCHOR_MS` baked in, the manual "click sync now" controls became dead weight. Removed entirely.

## Current state (as of 2026-04-30)

- Page is live, auto-syncs from baked-in anchor.
- Cycle precision: ~137ms per minute (noise floor).
- Anchor precision: probably good to a few seconds, calibrated against one user observation.
- 24 / 24 hours fully measured. 1439 / 1440 minute slots directly observed (one interpolated).

## Known limitations / open questions

1. **Cycle drift over time.** Our 4322.349s might be off by 1-2 seconds. Across many days, the page will drift relative to in-game. We'd know if the user notices the page being off again. Fix: another OCR session weeks/months later, refit cycle length jointly with anchor.
2. **Server maintenance behavior** — we hypothesized D2 keeps the cycle running through maintenance (since it's a function of UTC), but haven't verified. Tuesday's maintenance was the test we never got to confirm.
3. **The two-bump dawn/dusk shape.** No physical model fits cleanly. The dominant 12-hour Fourier component only explains 53% of variance; another 27% sits in the 8-hour harmonic. There may be a sun-position model with two distinct phases (day/night) that fits, but we didn't crack it. Could try **PySR** for symbolic regression if curiosity strikes.
4. **`tools/fix_ocr.py` doesn't exist yet.** All the digit-edit-1 / digit-edit-2 / "drop misreads" logic is in scratch scripts. If we re-OCR, we need to re-derive it or commit it.
5. **`build_durations.py` only emits per-hour by default.** Per-minute path requires `--minute` flag and outputs in fractional seconds, not ms. The actual ms-precise minute array we use was generated by ad-hoc scripts in chat. Should consolidate.

## Files of note

- `script.js` — the page itself.
- `index.html`, `style.css` — UI.
- `tools/ocr_clock.py` — OCR driver.
- `tools/build_durations.py` — analyzer (per-hour-focused; per-minute is ad-hoc).
- `minutes.csv`, `minutes_lowthresh.csv`, `minutes_final.csv`, `minutes_clean_v2.csv`, `minutes_clean_v3.csv` — various stages of OCR cleanup. `minutes_final.csv` is the canonical source for `MINUTE_DURATIONS_MS`.
- `minute_durations.csv` — the 1440-row clean dataset (minute_index, hour, minute, duration_ms, n_observations). Useful for further analysis.
- `fit_models.py` — parametric-fit experiments.
- `cherry/` — frame samples extracted from the recording for OCR validation; can be deleted if desired.

## How to redo this

If we ever record a new session for recalibration:

```powershell
# 1. Record D2 with inventory open (30+ min, ideally 2-3 cycles).
# 2. Find clock bbox:
python tools/ocr_clock.py "C:\path\to\recording.mp4" --pick-bbox

# 3. OCR with low diff threshold (catches subtle digit transitions):
python tools/ocr_clock.py "C:\path\to\recording.mp4" --bbox X,Y,W,H --upscale 4.0 --diff-threshold 1.0 -o minutes.csv

# 4. (manual) Apply the digit-edit-1 fixer to clean systematic misreads.

# 5. Generate JS arrays + anchor:
python tools/build_durations.py minutes_clean.csv --minute --anchor-time '...' > new.js

# 6. Paste MINUTE_DURATIONS_MS and DEFAULT_ANCHOR_MS into script.js, adjusting to ms units.
# 7. Verify against in-game observation, calibrate anchor if needed.
```

The bottleneck is the manual digit-edit fixer step. Worth building into a tool next time.

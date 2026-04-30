# Tools

## ocr_clock.py

Extracts (real-time, in-game-time) pairs from a screen recording of The Division 2 with the inventory open (clock visible).

### One-time setup

1. Install Tesseract for Windows: `winget install UB-Mannheim.TesseractOCR`. The script auto-detects the default install path. If you put it elsewhere, set `TESSERACT_CMD=C:\path\to\tesseract.exe`.
2. Install Python deps: `pip install -r tools/requirements.txt`.

### Usage

Find the bounding box of the clock in your recording (drag a rectangle, press Enter):

```
python tools/ocr_clock.py recording.mp4 --pick-bbox
```

It prints something like `--bbox 1820,40,80,30`. Reuse those numbers for the OCR pass:

```
python tools/ocr_clock.py recording.mp4 --bbox 1820,40,80,30 --output minutes.csv
```

The CSV looks like:

```
# anchor_time=2026-04-30T18:13:42.123Z
video_ms,ingame
0,14:41
3157,14:42
6403,14:43
...
```

`video_ms` is real time elapsed since the start of the recording. Subtract adjacent rows to get the duration of each in-game minute.

The `# anchor_time=...` header is auto-derived from the file's modification time minus its video duration (so for most screen recorders it's the moment you hit Record). `build_durations.py` reads this automatically.

### Useful flags

- `--debug-dir DIR` saves a cropped PNG for every frame OCR ran on, named with the parsed time. Lets you spot-check accuracy.
- `--diff-threshold N` raises (less OCR, may miss transitions) or lowers (more OCR, more robust) the pixel-change threshold needed to attempt OCR. Default 5.0 is conservative.
- `--every-n-frames N` skips frames. At 60fps source, `--every-n-frames 4` is usually fine since minutes change every ~3 real seconds.
- `--upscale 2.0` (default) bicubic-upscales the crop before OCR. Tesseract handles small text poorly; 2x is usually the sweet spot.

### After extraction

Run `build_durations.py` on the CSV to get a paste-ready JS array.

## build_durations.py

Reads `minutes.csv` and emits an updated `HOUR_DURATIONS` (and optionally `MINUTE_DURATIONS`) array suitable for pasting into `script.js`. Stdlib only, no install needed.

```
python tools/build_durations.py minutes.csv                     # hour array + auto-anchor
python tools/build_durations.py minutes.csv --minute            # also per-minute
python tools/build_durations.py minutes.csv > new_arrays.js     # redirect
```

If the CSV has an `# anchor_time=...` header (which `ocr_clock.py` writes by default), the script also emits a `DEFAULT_ANCHOR_MS` constant. Override with `--anchor-time '2026-04-30T18:13:42Z'` if you want a different anchor.

Stats and a per-hour delta-vs-2021 chart go to stderr, so redirecting stdout gives you a clean JS file.

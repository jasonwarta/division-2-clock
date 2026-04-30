#!/usr/bin/env python3
"""OCR a Division 2 in-game clock from a screen recording.

Reads each frame's clock region, detects when the displayed minute changes,
and writes a CSV row of (video_ms, ingame_HH:MM) at every detected transition.

Usage:
    # First, find the bounding box of the clock in your recording:
    python ocr_clock.py recording.mp4 --pick-bbox

    # Then run the OCR pass with that bbox:
    python ocr_clock.py recording.mp4 --bbox 1820,40,80,30 --output minutes.csv

    # Optional: --debug-dir DIR saves crops of every frame OCR was run on,
    # so you can spot-check accuracy.
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import pytesseract

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
TESSERACT_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789:"


def configure_tesseract():
    """Point pytesseract at the system tesseract binary on Windows."""
    override = os.environ.get("TESSERACT_CMD")
    if override:
        pytesseract.pytesseract.tesseract_cmd = override
        return
    if sys.platform == "win32":
        default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if Path(default_path).exists():
            pytesseract.pytesseract.tesseract_cmd = default_path


def parse_bbox(s):
    parts = s.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be 'X,Y,W,H'")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("bbox values must be integers")


def ocr_time(gray_crop):
    text = pytesseract.image_to_string(gray_crop, config=TESSERACT_CONFIG).strip()
    m = TIME_RE.match(text)
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return (h, mm)
    return None


def pick_bbox(video_path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        sys.exit(f"Could not open {video_path}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("Could not read first frame")

    print("Drag a rectangle around the clock, then press ENTER. ESC to cancel.", file=sys.stderr)
    bbox = cv2.selectROI("Select clock region", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()
    x, y, w, h = bbox
    if w == 0 or h == 0:
        sys.exit("No region selected")
    print(f"--bbox {x},{y},{w},{h}")


# Win11 Snipping Tool's in-progress placeholder file is named with the recording
# start time in UTC at sub-second precision -- e.g. "20260430-1813-30.7945725.mp4".
# The placeholder typically vanishes when the recording is finalized, so we don't
# scan for it; but if the user copies/renames the final file using this pattern
# we recognize it.
SNIPPING_TOOL_NAME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})-(\d+(?:\.\d+)?)\.mp4$")


def parse_snipping_tool_filename(name):
    """If 'name' matches the YYYYMMDD-HHMM-SS.SSSSSSS.mp4 pattern, return a
    timezone-aware UTC datetime. Otherwise None."""
    m = SNIPPING_TOOL_NAME_RE.match(name)
    if not m:
        return None
    y, mo, d, h, mi, s_str = m.groups()
    try:
        sec_f = float(s_str)
        sec_int = int(sec_f)
        usec = int(round((sec_f - sec_int) * 1_000_000))
        return datetime(int(y), int(mo), int(d), int(h), int(mi), sec_int, usec, tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None


def infer_start_time_iso(video_path, fps, total_frames):
    """Infer wall-clock time when frame 0 was recorded.

    Preference order:
      1. The video's own filename, if it matches Snipping Tool's pattern.
      2. mtime - duration (fallback).

    Returns ISO 8601 UTC string with ms precision, or None.
    """
    if fps <= 0 or total_frames <= 0:
        return None

    # The video file may already be named in Snipping Tool's format if the user
    # renamed it that way or copied the placeholder file out before stopping.
    name_match = parse_snipping_tool_filename(Path(video_path).name)
    if name_match is not None:
        return name_match.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    duration_sec = total_frames / fps
    try:
        mtime = os.path.getmtime(video_path)
    except OSError:
        return None
    start_unix = mtime - duration_sec
    if start_unix <= 0:
        return None
    dt = datetime.fromtimestamp(start_unix, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_ocr(args):
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        sys.exit(f"Could not open {args.video}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    x, y, w, h = args.bbox
    print(
        f"Video: {fps:.2f} fps, {total_frames} frames, ~{total_frames / fps / 60:.1f} min",
        file=sys.stderr,
    )
    print(f"Clock region: x={x}, y={y}, w={w}, h={h}", file=sys.stderr)

    inferred_start = infer_start_time_iso(args.video, fps, total_frames)
    if inferred_start:
        print(f"Inferred recording start: {inferred_start}", file=sys.stderr)
    else:
        print("Could not infer recording start time from file metadata.", file=sys.stderr)

    if args.debug_dir:
        args.debug_dir.mkdir(parents=True, exist_ok=True)

    out_handle = open(args.output, "w", newline="") if args.output else sys.stdout
    if inferred_start:
        # Embed the start time as a comment header so build_durations.py can
        # pick it up automatically without the user having to pass it again.
        out_handle.write(f"# anchor_time={inferred_start}\n")
    writer = csv.writer(out_handle)
    writer.writerow(["video_ms", "ingame"])

    prev_gray = None
    last_emitted = None
    frame_idx = 0
    transitions = 0
    ocr_calls = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_idx % args.every_n_frames != 0:
                frame_idx += 1
                continue

            crop = frame[y : y + h, x : x + w]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            if prev_gray is None:
                triggered = True
            else:
                triggered = float(cv2.absdiff(gray, prev_gray).mean()) > args.diff_threshold

            if triggered:
                if args.upscale != 1.0:
                    target = (
                        int(gray.shape[1] * args.upscale),
                        int(gray.shape[0] * args.upscale),
                    )
                    upscaled = cv2.resize(gray, target, interpolation=cv2.INTER_CUBIC)
                else:
                    upscaled = gray

                ocr_calls += 1
                result = ocr_time(upscaled)
                if result is not None and result != last_emitted:
                    ms = int(round((frame_idx / fps) * 1000))
                    writer.writerow([ms, f"{result[0]:02d}:{result[1]:02d}"])
                    if args.output:
                        out_handle.flush()
                    if args.debug_dir:
                        debug_path = args.debug_dir / f"{ms:010d}_{result[0]:02d}{result[1]:02d}.png"
                        cv2.imwrite(str(debug_path), crop)
                    last_emitted = result
                    transitions += 1

            prev_gray = gray
            frame_idx += 1

            if frame_idx % 500 == 0 and total_frames:
                pct = (frame_idx / total_frames) * 100
                sys.stderr.write(
                    f"\r{frame_idx}/{total_frames} ({pct:.1f}%) - "
                    f"{ocr_calls} OCRs, {transitions} transitions"
                )
                sys.stderr.flush()
    finally:
        sys.stderr.write("\n")
        cap.release()
        if args.output:
            out_handle.close()

    print(
        f"Done: {frame_idx} frames processed, {ocr_calls} OCR calls, {transitions} transitions written.",
        file=sys.stderr,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path, help="Input video file (mp4, mkv, etc.)")
    ap.add_argument("--bbox", type=parse_bbox, help="Clock region: X,Y,W,H in pixels")
    ap.add_argument("--output", "-o", type=Path, help="Output CSV path (default: stdout)")
    ap.add_argument(
        "--diff-threshold",
        type=float,
        default=5.0,
        help="Mean abs pixel diff (0-255) needed to trigger OCR. Lower = more OCR (default 5.0)",
    )
    ap.add_argument(
        "--every-n-frames",
        type=int,
        default=1,
        help="Process every Nth frame. Raise to skip work on high-fps recordings (default 1)",
    )
    ap.add_argument(
        "--upscale",
        type=float,
        default=2.0,
        help="Upscale factor for the crop before OCR (default 2.0). Helps Tesseract on small text.",
    )
    ap.add_argument("--debug-dir", type=Path, help="Save cropped frames where OCR ran")
    ap.add_argument(
        "--pick-bbox",
        action="store_true",
        help="Open a preview window on the first frame so you can drag a clock bounding box. Prints the resulting --bbox argument and exits.",
    )
    args = ap.parse_args()

    configure_tesseract()

    if args.pick_bbox:
        pick_bbox(args.video)
        return

    if args.bbox is None:
        ap.error("--bbox is required (or use --pick-bbox to find one interactively)")

    run_ocr(args)


if __name__ == "__main__":
    main()

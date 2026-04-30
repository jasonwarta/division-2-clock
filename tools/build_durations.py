#!/usr/bin/env python3
"""Turn a minutes.csv (output of ocr_clock.py) into JS duration arrays.

For each pair of adjacent rows whose in-game times differ by exactly one
minute, the elapsed real time is attributed to the earlier minute slot.
Multiple observations of the same slot (across cycles) are averaged.
The script then emits a paste-ready HOUR_DURATIONS array and, with --minute,
a per-minute MINUTE_DURATIONS array.

Usage:
    python tools/build_durations.py minutes.csv
    python tools/build_durations.py minutes.csv --minute > new_durations.js

Stats and per-hour deltas vs. the 2021 data go to stderr so they don't
contaminate stdout when redirecting.
"""
import argparse
import csv
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Current 2021 values from script.js, for delta reporting.
CURRENT_HOUR_DURATIONS = [
    135, 132, 131, 136, 144, 162, 218, 276,
    311, 281, 178, 139, 128, 125, 130, 147,
    205, 321, 291, 244, 150, 116, 108, 111,
]


def parse_csv(path):
    """Returns (rows, embedded_anchor_time).

    Skips '# key=value' header comments at the top of the file, extracting
    'anchor_time' if present. Then reads the regular CSV body.
    """
    rows = []
    embedded_anchor_time = None
    with open(path, newline="") as f:
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                break
            stripped = line.strip()
            if stripped.startswith("#"):
                content = stripped.lstrip("#").strip()
                if content.startswith("anchor_time="):
                    embedded_anchor_time = content.split("=", 1)[1].strip()
                continue
            f.seek(pos)
            break
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ms = int(row["video_ms"])
                h, m = row["ingame"].split(":")
                rows.append((ms, int(h), int(m)))
            except (KeyError, ValueError):
                continue
    rows.sort()
    return rows, embedded_anchor_time


def compute_minute_durations(rows, max_sane_duration_sec):
    """Record the duration of each observed in-game minute.

    A minute's duration is only counted when *both* the transition INTO it
    and the transition OUT of it are present in the data (each as a clean
    1-minute step from the previous row). This rejects:

      - The first row of the recording (we don't know when that minute
        started -- it was already on screen when capture began).
      - Any row where the previous row jumped by more than 1 minute, e.g.
        because the clock was hidden behind a closed menu, the player was
        AFK-kicked and reconnected, or OCR briefly missed transitions.

    For those rows we know neither when the displayed minute started nor
    how long it had already been visible, so attributing any duration to
    that minute slot would be inaccurate. We wait for the next clean
    transition out and start recording from there.
    """
    durations = defaultdict(list)
    skipped_gaps = 0
    skipped_outliers = 0
    skipped_post_gap_starts = 0

    def minute_diff(prev, curr):
        d = (curr[1] * 60 + curr[2]) - (prev[1] * 60 + prev[2])
        if d < 0:
            d += 1440
        return d

    # Iterate over each row that has both a predecessor and a successor.
    # Row[i] represents some minute slot; we record its duration only if:
    #   1. transition (i-1 -> i) was a clean 1-minute step (so we observed
    #      the moment it started), AND
    #   2. transition (i -> i+1) is a clean 1-minute step (so we observed
    #      the moment it ended).
    for i in range(1, len(rows) - 1):
        prev, curr, nxt = rows[i - 1], rows[i], rows[i + 1]

        if minute_diff(prev, curr) != 1:
            skipped_post_gap_starts += 1
            continue

        if minute_diff(curr, nxt) != 1:
            skipped_gaps += 1
            continue

        duration_ms = nxt[0] - curr[0]
        if duration_ms <= 0 or duration_ms > max_sane_duration_sec * 1000:
            skipped_outliers += 1
            continue

        durations[(curr[1], curr[2])].append(duration_ms)

    return durations, skipped_gaps, skipped_outliers, skipped_post_gap_starts


def hour_summaries(per_minute):
    """For each hour, return (estimated_hour_duration_sec, observed_minute_count).

    Estimates the full-hour duration by averaging observed minute slots and
    extrapolating to 60. If all 60 minutes are covered, the result is exact.
    """
    out = []
    for h in range(24):
        observed_durations_ms = []
        for m in range(60):
            obs = per_minute.get((h, m), [])
            if obs:
                observed_durations_ms.append(statistics.mean(obs))
        if observed_durations_ms:
            avg_minute_ms = sum(observed_durations_ms) / len(observed_durations_ms)
            hour_sec = (avg_minute_ms * 60) / 1000
            out.append((hour_sec, len(observed_durations_ms)))
        else:
            out.append((None, 0))
    return out


def emit_hour_array(hour_summary, file=sys.stdout):
    file.write("// Updated HOUR_DURATIONS (real seconds per in-game hour, integer-rounded).\n")
    file.write("const HOUR_DURATIONS = [\n")
    for h, (dur, obs) in enumerate(hour_summary):
        if dur is None:
            file.write(f"  null, // hour {h:02d}: no data\n")
            continue
        old = CURRENT_HOUR_DURATIONS[h]
        delta = dur - old
        file.write(
            f"  {round(dur)}, // hour {h:02d}: {dur:6.2f}s "
            f"({delta:+5.1f} vs 2021), obs {obs:2d}/60 min\n"
        )
    file.write("];\n")


def ingame_to_real_seconds(hour, minute, hour_durations):
    """Mirror of script.js ingameToReal()."""
    cum = sum(hour_durations[:hour])
    cum += (minute / 60) * hour_durations[hour]
    return cum


def parse_iso_to_utc_ms(iso):
    """Accept '2026-04-30T12:00:00Z' or '2026-04-30T12:00:00+00:00' etc."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"Could not parse --anchor-time: {iso!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def emit_anchor(anchor_ms, recording_start_iso, observation, hour_durations, file=sys.stdout):
    h, m, video_ms = observation
    file.write("\n// Auto-anchor: Unix ms at the moment in-game was 00:00:00.\n")
    file.write(f"// Derived from observation: at {recording_start_iso}+{video_ms}ms, in-game was {h:02d}:{m:02d}.\n")
    file.write(f"const DEFAULT_ANCHOR_MS = {int(anchor_ms)};\n")


def emit_minute_array(per_minute, file=sys.stdout):
    file.write("\n// Per-minute MINUTE_DURATIONS (real seconds, 3 decimals).\n")
    file.write("// null = no observation in this slot.\n")
    file.write("const MINUTE_DURATIONS = [\n")
    for h in range(24):
        vals = []
        for m in range(60):
            obs = per_minute.get((h, m), [])
            if obs:
                vals.append(f"{statistics.mean(obs) / 1000:.3f}")
            else:
                vals.append("null")
        file.write(f"  // hour {h:02d}\n")
        file.write("  " + ", ".join(vals) + ",\n")
    file.write("];\n")


def emit_stats(
    rows, per_minute, hour_summary, skipped_gaps, skipped_outliers, skipped_post_gap_starts,
    file=sys.stderr,
):
    bar = "=" * 64
    total_obs = sum(len(v) for v in per_minute.values())
    minutes_covered = len(per_minute)
    hours_covered = sum(1 for d, _ in hour_summary if d is not None)

    new_total = sum(d for d, _ in hour_summary if d is not None)
    old_total = sum(
        CURRENT_HOUR_DURATIONS[h] for h, (d, _) in enumerate(hour_summary) if d is not None
    )

    print(bar, file=file)
    print(f"Rows read:                {len(rows)}", file=file)
    print(f"Reliable durations:       {total_obs}", file=file)
    print(f"Skipped (gap before row): {skipped_post_gap_starts}", file=file)
    print(f"Skipped (gap after row):  {skipped_gaps}", file=file)
    print(f"Skipped (outliers):       {skipped_outliers}", file=file)
    print(f"Minutes covered:          {minutes_covered}/1440", file=file)
    print(f"Hours with any coverage:  {hours_covered}/24", file=file)
    print(
        f"Cycle total (covered):    new={new_total:.1f}s, 2021={old_total}s, "
        f"delta={new_total - old_total:+.1f}s",
        file=file,
    )
    print(bar, file=file)
    print("Per-hour comparison (covered hours only):", file=file)
    for h, (dur, obs) in enumerate(hour_summary):
        if dur is None:
            continue
        old = CURRENT_HOUR_DURATIONS[h]
        delta = dur - old
        bar_chars = "+" * min(int(abs(delta)), 40) if delta >= 0 else "-" * min(int(abs(delta)), 40)
        print(
            f"  {h:02d}: 2021={old:3d}s  new={dur:6.2f}s  delta={delta:+6.2f}s  "
            f"obs={obs:2d}/60  {bar_chars}",
            file=file,
        )
    print(bar, file=file)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("csv_path", type=Path, help="Path to minutes.csv (from ocr_clock.py)")
    ap.add_argument(
        "--minute",
        action="store_true",
        help="Also emit per-minute MINUTE_DURATIONS (1440 entries).",
    )
    ap.add_argument(
        "--max-duration",
        type=float,
        default=30.0,
        help="Reject adjacent-minute spans longer than this many seconds as outliers (default 30).",
    )
    ap.add_argument(
        "--anchor-time",
        help="ISO 8601 wall-clock time corresponding to video_ms=0 (recording start). "
        "Overrides the # anchor_time= header that ocr_clock.py writes into the CSV. "
        "If neither is provided, no DEFAULT_ANCHOR_MS is emitted.",
    )
    args = ap.parse_args()

    rows, embedded_anchor_time = parse_csv(args.csv_path)
    if not rows:
        sys.exit("No usable rows in CSV.")

    per_minute, skipped_gaps, skipped_outliers, skipped_post_gap_starts = compute_minute_durations(
        rows, args.max_duration
    )
    hour_summary = hour_summaries(per_minute)

    emit_stats(
        rows, per_minute, hour_summary, skipped_gaps, skipped_outliers, skipped_post_gap_starts
    )
    emit_hour_array(hour_summary)
    if args.minute:
        emit_minute_array(per_minute)

    anchor_time = args.anchor_time or embedded_anchor_time
    if anchor_time:
        if embedded_anchor_time and not args.anchor_time:
            print(f"Using embedded anchor_time from CSV: {embedded_anchor_time}", file=sys.stderr)
        recording_start_ms = parse_iso_to_utc_ms(anchor_time)
        merged_durations = [
            round(d) if d is not None else CURRENT_HOUR_DURATIONS[h]
            for h, (d, _) in enumerate(hour_summary)
        ]
        # Use the SECOND row (the first observed time-change), not the first.
        # The first row was captured at video_ms=0 mid-way through some minute,
        # so its anchor implication is uncertain by up to one minute. The second
        # row's ms is the moment OCR first detected a *different* time, which is
        # closer to a true minute-transition boundary.
        anchor_row_idx = 1 if len(rows) >= 2 else 0
        ms, h, m = rows[anchor_row_idx]
        wall_clock_ms = recording_start_ms + ms
        ingame_offset_sec = ingame_to_real_seconds(h, m, merged_durations)
        anchor_ms = wall_clock_ms - ingame_offset_sec * 1000
        emit_anchor(anchor_ms, anchor_time, (h, m, ms), merged_durations)


if __name__ == "__main__":
    main()

// Real seconds per in-game hour, indexed 0..23.
// Source: OCR pass over a 2.5-hour screen recording (2026-04-30) covering ~2
// full cycles, averaged across 30+ observations per hour. Each value is
// within ~6s of the 2021 dataset, confirming the cycle structure was right;
// these new values just have ms-precision instead of +-2-3 sec hand-timing.
// See tools/ocr_clock.py and tools/build_durations.py for the pipeline.
const HOUR_DURATIONS = [
  135, 131, 132, 136, 145, 163, 222, 275,
  315, 275, 175, 139, 127, 125, 131, 149,
  210, 324, 295, 238, 148, 115, 108, 111,
];

const CYCLE_SECONDS = HOUR_DURATIONS.reduce((a, b) => a + b, 0); // 4319

// START_CUM[h] = real seconds elapsed at the moment in-game time becomes h:00:00.
// START_CUM[0] = 0; START_CUM[24] = CYCLE_SECONDS.
const START_CUM = [0];
for (const d of HOUR_DURATIONS) START_CUM.push(START_CUM[START_CUM.length - 1] + d);

// Auto-anchor: real-world Unix ms at the moment in-game was 00:00:00.
// Derived from a 2.5-hour OCR session on 2026-04-30. Anchored on the first
// observed minute-transition (05:51 -> 05:52 at video_ms=2633) rather than
// on the recording's first frame, since the first frame fell mid-minute and
// its anchor implication was uncertain by up to 60 real seconds.
const ANCHOR_MS = 1777571993160;

function realToIngame(elapsedRealSec) {
  const e = ((elapsedRealSec % CYCLE_SECONDS) + CYCLE_SECONDS) % CYCLE_SECONDS;
  let h = 0;
  while (h < 23 && START_CUM[h + 1] <= e) h++;
  const intoHour = e - START_CUM[h];
  const fraction = intoHour / HOUR_DURATIONS[h];
  const ingameSecondsTotal = Math.floor(fraction * 3600);
  const minute = Math.floor(ingameSecondsTotal / 60);
  const second = ingameSecondsTotal % 60;
  return {
    hour: h,
    minute: minute,
    second: second,
    fractionOfDay: e / CYCLE_SECONDS,
    fractionOfHour: fraction,
  };
}

function pad(n, w) {
  if (w === undefined) w = 2;
  return String(n).padStart(w, "0");
}

function formatIngame(t) {
  return pad(t.hour) + ":" + pad(t.minute) + ":" + pad(t.second);
}

function phaseLabel(hour) {
  if (hour >= 5 && hour < 7) return "Dawn";
  if (hour >= 7 && hour < 18) return "Day";
  if (hour >= 18 && hour < 20) return "Dusk";
  return "Night";
}

function format12h(date) {
  let h = date.getHours();
  const m = date.getMinutes();
  const ampm = h >= 12 ? "pm" : "am";
  h = h % 12;
  if (h === 0) h = 12;
  return h + ":" + pad(m) + ampm;
}

function formatOffset(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + "s";
  const m = Math.floor(s / 60);
  if (m < 60) return m + "min";
  const h = Math.floor(m / 60);
  const rem = m % 60;
  if (rem === 0) return h + "hr";
  return h + "hr" + rem + "min";
}

// Real-time when in-game hour h:00 starts, for the entry at index i in a timeline
// that begins at currentHour (so i=0 -> current hour, in the current cycle).
function timelineHourStart(i, currentHour, nowMs) {
  const elapsedSec = (nowMs - ANCHOR_MS) / 1000;
  const cyclesPassed = Math.floor(elapsedSec / CYCLE_SECONDS);
  const cycleStartMs = ANCHOR_MS + cyclesPassed * CYCLE_SECONDS * 1000;
  const cycleOffset = Math.floor((currentHour + i) / 24);
  const h = (currentHour + i) % 24;
  return new Date(cycleStartMs + (cycleOffset * CYCLE_SECONDS + START_CUM[h]) * 1000);
}

const els = {
  clock: document.getElementById("clock"),
  phase: document.getElementById("phase"),
  timeline: document.getElementById("timeline"),
  timelineRows: document.getElementById("timeline-rows"),
  timelineMarker: document.querySelector(".timeline-marker"),
};

// Must match .timeline-row height in style.css.
const ROW_HEIGHT_PX = 60;
let prevCurrentHour = null;

function renderTimeline(nowMs, currentHour) {
  const rows = [];
  for (let i = 0; i < 24; i++) {
    const h = (currentHour + i) % 24;
    const isCurrent = i === 0;
    const when = timelineHourStart(i, currentHour, nowMs);
    const deltaSec = Math.abs((when.getTime() - nowMs) / 1000);
    const metaHtml =
      '<div class="timeline-meta">' +
      format12h(when) +
      " &middot; " +
      formatOffset(deltaSec) +
      "</div>";
    rows.push(
      '<div class="timeline-row' +
        (isCurrent ? " current" : "") +
        '">' +
        '<div class="timeline-tick"></div>' +
        '<div class="timeline-hour">' +
        pad(h) +
        ":00</div>" +
        metaHtml +
        "</div>"
    );
  }
  els.timelineRows.innerHTML = rows.join("");
}

// Slide the timeline rows upward as the in-game minute progresses, so the
// current hour starts at the marker line and slides up past it, fading at
// the top, while the next hour rises into its place by the end of the hour.
function updateTimelineSlide(t) {
  const offsetPx = t.fractionOfHour * ROW_HEIGHT_PX;
  const transform = "translateY(" + (-offsetPx).toFixed(3) + "px)";

  if (prevCurrentHour !== t.hour) {
    // Timeline just re-rendered with a new currentHour at row 0. The transform
    // would otherwise animate from ~-60px back toward 0, looking like the list
    // jumps backward. Snap without transition.
    els.timelineRows.style.transition = "none";
    els.timelineRows.style.transform = transform;
    void els.timelineRows.offsetHeight;
    els.timelineRows.style.transition = "";
  } else {
    els.timelineRows.style.transform = transform;
  }
  prevCurrentHour = t.hour;
}

function tick() {
  const nowMs = Date.now();
  const elapsed = (nowMs - ANCHOR_MS) / 1000;
  const t = realToIngame(elapsed);

  els.clock.textContent = formatIngame(t);
  els.phase.textContent = phaseLabel(t.hour);

  renderTimeline(nowMs, t.hour);
  updateTimelineSlide(t);
}

tick();
setInterval(tick, 500);

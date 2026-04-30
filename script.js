// Real ms per in-game hour, indexed 0..23.
// Source: OCR pass over a 2.5-hour screen recording (2026-04-30) covering ~2
// full cycles, averaged across 30+ minute observations per hour.
// Tracking in ms (not rounded seconds) preserves the OCR's frame-level
// precision (33ms per frame at 30fps).
const HOUR_DURATIONS_MS = [
  135333, 131488, 131849, 135546, 144515, 163304, 222190, 275122,
  315272, 275274, 175304, 138740, 127167, 124998, 130668, 148697,
  210059, 324436, 294545, 237819, 147909, 115181, 108002, 111485,
];

const CYCLE_MS = HOUR_DURATIONS_MS.reduce((a, b) => a + b, 0); // 4324903

// START_CUM_MS[h] = real ms elapsed at the moment in-game time becomes h:00:00.
const START_CUM_MS = [0];
for (const d of HOUR_DURATIONS_MS) START_CUM_MS.push(START_CUM_MS[START_CUM_MS.length - 1] + d);

// Auto-anchor: real-world Unix ms at the moment in-game was 00:00:00.
// Derived from the OCR session and calibrated against a user observation:
// at 22:32 UTC the page showed ~18:13 while in-game showed 18:17 (4 in-game
// min behind). At hour 18 (294.5s/hour), 4 in-game min = 19.636 real sec,
// so the anchor needs to be 19636ms EARLIER than the OCR-derived value.
//   OCR-derived (from row[1] of minutes.csv): 1777571993160
//   Calibration shift: -19636 ms
const ANCHOR_MS = 1777571973524;

function realToIngame(elapsedRealMs) {
  const e = ((elapsedRealMs % CYCLE_MS) + CYCLE_MS) % CYCLE_MS;
  let h = 0;
  while (h < 23 && START_CUM_MS[h + 1] <= e) h++;
  const intoHour = e - START_CUM_MS[h];
  const fraction = intoHour / HOUR_DURATIONS_MS[h];
  const ingameSecondsTotal = Math.floor(fraction * 3600);
  const minute = Math.floor(ingameSecondsTotal / 60);
  const second = ingameSecondsTotal % 60;
  return {
    hour: h,
    minute: minute,
    second: second,
    fractionOfDay: e / CYCLE_MS,
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
  const elapsedMs = nowMs - ANCHOR_MS;
  const cyclesPassed = Math.floor(elapsedMs / CYCLE_MS);
  const cycleStartMs = ANCHOR_MS + cyclesPassed * CYCLE_MS;
  const cycleOffset = Math.floor((currentHour + i) / 24);
  const h = (currentHour + i) % 24;
  return new Date(cycleStartMs + cycleOffset * CYCLE_MS + START_CUM_MS[h]);
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
  const elapsedMs = nowMs - ANCHOR_MS;
  const t = realToIngame(elapsedMs);

  els.clock.textContent = formatIngame(t);
  els.phase.textContent = phaseLabel(t.hour);

  renderTimeline(nowMs, t.hour);
  updateTimelineSlide(t);
}

tick();
setInterval(tick, 500);

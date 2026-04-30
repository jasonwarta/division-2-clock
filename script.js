// Real seconds per in-game hour, indexed 0..23.
// Source: third dataset from "210614 ingame time" (timed against captured footage,
// noted as the most accurate of the three runs in the spreadsheet).
// See https://www.reddit.com/r/thedivision/comments/o0a3x0/
const HOUR_DURATIONS = [
  135, 132, 131, 136, 144, 162, 218, 276,
  311, 281, 178, 139, 128, 125, 130, 147,
  205, 321, 291, 244, 150, 116, 108, 111,
];

const CYCLE_SECONDS = HOUR_DURATIONS.reduce((a, b) => a + b, 0); // 4319

// START_CUM[h] = real seconds elapsed at the moment in-game time becomes h:00:00.
// START_CUM[0] = 0; START_CUM[24] = CYCLE_SECONDS.
const START_CUM = [0];
for (const d of HOUR_DURATIONS) START_CUM.push(START_CUM[START_CUM.length - 1] + d);

const ANCHOR_KEY = "div2clock.anchorMs";

function loadAnchor() {
  const raw = localStorage.getItem(ANCHOR_KEY);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function saveAnchor(ms) {
  localStorage.setItem(ANCHOR_KEY, String(ms));
}

function clearAnchor() {
  localStorage.removeItem(ANCHOR_KEY);
}

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

function ingameToReal(hour, minute) {
  return START_CUM[hour] + (minute / 60) * HOUR_DURATIONS[hour];
}

function parseHHMM(s) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h < 0 || h > 23 || min < 0 || min > 59) return null;
  return { hour: h, minute: min };
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
function timelineHourStart(i, currentHour, anchorMs, nowMs) {
  const elapsedSec = (nowMs - anchorMs) / 1000;
  const cyclesPassed = Math.floor(elapsedSec / CYCLE_SECONDS);
  const cycleStartMs = anchorMs + cyclesPassed * CYCLE_SECONDS * 1000;
  const cycleOffset = Math.floor((currentHour + i) / 24);
  const h = (currentHour + i) % 24;
  return new Date(cycleStartMs + (cycleOffset * CYCLE_SECONDS + START_CUM[h]) * 1000);
}

const els = {
  clock: document.getElementById("clock"),
  phase: document.getElementById("phase"),
  syncMidnight: document.getElementById("sync-midnight"),
  syncCustom: document.getElementById("sync-custom"),
  syncTime: document.getElementById("sync-time"),
  clearAnchor: document.getElementById("clear-anchor"),
  syncHint: document.getElementById("sync-hint"),
  timeline: document.getElementById("timeline"),
  timelineRows: document.getElementById("timeline-rows"),
};

// Must match .timeline-row height in style.css.
const ROW_HEIGHT_PX = 60;
let prevCurrentHour = null;

function renderTimeline(anchorMs, nowMs, currentHour) {
  const rows = [];
  for (let i = 0; i < 24; i++) {
    const h = (currentHour + i) % 24;
    const isCurrent = i === 0;
    let metaHtml = "";
    if (anchorMs != null) {
      const when = timelineHourStart(i, currentHour, anchorMs, nowMs);
      const deltaSec = Math.abs((when.getTime() - nowMs) / 1000);
      metaHtml =
        '<div class="timeline-meta">' +
        format12h(when) +
        " &middot; " +
        formatOffset(deltaSec) +
        "</div>";
    }
    rows.push(
      '<div class="timeline-row' +
        (isCurrent ? " current" : "") +
        '">' +
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
// current hour fades out the top of the viewport over the course of the hour
// and the next hour scrolls into the visible area from below.
function updateTimelineSlide(t) {
  if (!t) {
    els.timelineRows.style.transform = "";
    prevCurrentHour = null;
    return;
  }

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
  const anchorMs = loadAnchor();
  const nowMs = Date.now();
  let currentHour = 0;
  let t = null;

  if (anchorMs == null) {
    els.clock.textContent = "--:--:--";
    els.clock.classList.remove("synced");
    els.phase.textContent = "Not synced";
    els.syncHint.style.display = "";
  } else {
    const elapsed = (nowMs - anchorMs) / 1000;
    t = realToIngame(elapsed);
    els.clock.textContent = formatIngame(t);
    els.clock.classList.add("synced");
    els.phase.textContent = phaseLabel(t.hour);
    els.syncHint.style.display = "none";
    currentHour = t.hour;
  }

  renderTimeline(anchorMs, nowMs, currentHour);
  updateTimelineSlide(t);
}

function setAnchorFromIngame(hour, minute) {
  const offsetSec = ingameToReal(hour, minute);
  const anchorMs = Date.now() - offsetSec * 1000;
  saveAnchor(anchorMs);
  tick();
}

els.syncMidnight.addEventListener("click", function () {
  setAnchorFromIngame(0, 0);
});

els.syncCustom.addEventListener("click", function () {
  const parsed = parseHHMM(els.syncTime.value);
  if (!parsed) {
    els.syncTime.focus();
    els.syncTime.select();
    return;
  }
  setAnchorFromIngame(parsed.hour, parsed.minute);
});

els.syncTime.addEventListener("keydown", function (e) {
  if (e.key === "Enter") els.syncCustom.click();
});

els.clearAnchor.addEventListener("click", function () {
  clearAnchor();
  tick();
});

tick();
setInterval(tick, 500);

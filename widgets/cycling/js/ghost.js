// Cycling — the ghost panel's arithmetic, ported from the source app's in-ride getters. data.py says which segment
// he is inside, how far he has ridden in it and the earlier attempts; this works out, every second, where each
// rival stands against him. A delta > 0 means that attempt was AHEAD of him at this point, < 0 that he leads it.

export const STAFF_WINDOW_S = 180;            // the staff shows ±3 min; anyone further goes to the overflow arrows
const LANE_X = [20, 40, 60, 80];

export function distInSeg(a) {
  if (!a) return 0;
  const total = a.distance_m || Math.max(1, a.dist_accum || 0);
  return Math.min(total, a.dist_accum || 0);
}

export function competitors(g, now) {
  const a = g && g.active;
  if (!a || !g.attempts || !g.attempts.length) return [];
  const elapsed = Math.round((now - a.entered_ms) / 1000);
  const progress = a.distance_m ? distInSeg(a) / a.distance_m : 0;
  return g.attempts.filter((att) => att.time_sec > 0).map((att) => {
    const deltaSec = elapsed - att.time_sec * progress;
    return { id: att.id, deltaSec, time_sec: att.time_sec, is_pr: !!att.is_pr, session_id: att.session_id,
      session_name: att.session_name, pctX: 50 + Math.max(-1, Math.min(1, deltaSec / 60)) * 50 };
  });
}

export function myY(rivals) {                 // first (nobody ahead) at the top, last at the bottom
  if (!rivals.length) return 50;
  const ahead = rivals.filter((r) => r.deltaSec > 0).length;
  return Math.round(12 + (ahead / rivals.length) * 76);
}

export function staff(rivals) {
  const me = myY(rivals);
  return rivals.filter((c) => Math.abs(c.deltaSec) <= STAFF_WINDOW_S).map((c, i) => {
    const offset = Math.max(-1, Math.min(1, c.deltaSec / STAFF_WINDOW_S));
    return { ...c, y: Math.max(6, Math.min(94, me - offset * 42)), x: LANE_X[Math.abs(Math.round(c.id || i)) % LANE_X.length],
      dir: c.deltaSec > 0 ? "ahead" : "behind" };
  });
}

export const beyondAhead = (r) => r.filter((c) => c.deltaSec > STAFF_WINDOW_S).length;
export const beyondBehind = (r) => r.filter((c) => c.deltaSec < -STAFF_WINDOW_S).length;
export const rank = (r) => r.filter((c) => c.deltaSec > 0).length + 1;
export function nextAhead(r) { const a = r.filter((c) => c.deltaSec > 0).sort((x, y) => x.deltaSec - y.deltaSec); return a[0] || null; }
export function nextBehind(r) { const b = r.filter((c) => c.deltaSec < 0).sort((x, y) => y.deltaSec - x.deltaSec); return b[0] || null; }

export function progressPct(a) {
  if (!a || !a.distance_m) return 0;
  return Math.min(100, Math.max(0, (distInSeg(a) / a.distance_m) * 100));
}

export function secToFinish(a, speedKmh) {    // the remaining distance at the current speed; stopped: no estimate
  if (!a || !a.distance_m) return null;
  const remain = a.distance_m - distInSeg(a);
  if (remain <= 0) return 0;
  if (!speedKmh || speedKmh < 1) return null;
  return remain / (speedKmh / 3.6);
}
export function nearFinish(a, speedKmh) { const s = secToFinish(a, speedKmh); return s != null && s >= 0 && s <= 30; }

export function fmtDist(m) { m = m || 0; return m >= 1000 ? (m / 1000).toFixed(2) + " km" : Math.round(m) + " m"; }

// The HR bar: where the heart rate sits against the zone, −2…+2 (0 the middle, ±1 the edges).
export function zonePosition(bpm, lo, hi) {
  if (!bpm || !lo || !hi) return 0;
  const half = (hi - lo) / 2;
  return Math.max(-2, Math.min(2, half ? (bpm - (lo + hi) / 2) / half : 0));
}

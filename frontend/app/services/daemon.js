// ============================================================================
// daemon.js — IS THE LOCAL DAEMON THERE, AND IF NOT, WHERE DOES ONE GET IT? (V2-575 · P1)
//
// The state half of the daemon surface: no DOM, no styling. `TopBar.js` renders the dot from `iconState()`
// and `DaemonSetup.js` renders everything else from `status()`.
//
// IT TALKS TO THE ENGINE, NEVER TO 45817. The daemon speaks plain http and this page may be served over
// https, so a direct call is mixed content; it is cross-origin, so it would need CORS headers the daemon
// must never send; and its bearer token would have to reach JavaScript, which is the last place a
// credential that reads somebody's documents should be. `server/daemon_api.py` holds all three problems.
//
// THE POLL IS THE `update/watch.js` PATTERN, for the same reasons written there: a hidden tab is not polled
// at all, a visible one costs one small JSON against a dict the engine already had, and it keeps working in
// a PWA whose tab has been backgrounded for hours. The state it watches changes on a human timescale
// (somebody installs a daemon, somebody picks a folder), so 20 s is generous rather than tight.
//
// ON A CLOUD ACCOUNT the engine answers `state: "remote"`: the daemon runs on the user's computer and the
// cloud engine is in a container somewhere else, with no path between them until the relay exists (P3). The
// icon still has a job there, and it is the one the operator asked for — it is where somebody working
// against the cloud agent gets the installer for their own machine.
import { createSignal } from "../core/reactive.js?v=2";
import { asleep } from "./presence.js?v=1";

const POLL_MS = 20000;
// While the daemon downloads a browser the progress is the only thing on this screen that moves, so it is asked
// for every 2 s — and only then: the fast poll re-arms from each answer and dies with the first one that is not
// `downloading`, so a finished (or abandoned) download costs nothing afterwards.
const DOWNLOAD_POLL_MS = 2000;
let _fast = null;

const [status, setStatus] = createSignal(null);
export { status };

let _iv = null;
let _last = "";   // the last payload, verbatim — see `check()`

export async function check() {
  try {
    const r = await fetch("/api/daemon/status", { cache: "no-store" });
    if (!r.ok) return;                       // engine restarting, or an older build without the route
    const s = await r.json();
    if (!s || !s.ok) return;
    _armDownloadPoll(s);
    // ⚠️ ONLY WHEN SOMETHING ACTUALLY CHANGED. The poll answers every 20 s with an equal-but-new object, and
    // the setup screen is a reactive child of this signal — so writing it unconditionally would rebuild that
    // subtree four times a minute and wipe whatever the user had half-typed into the folder field.
    const next = JSON.stringify(s);
    if (next === _last) return;
    _last = next;
    setStatus(s);
  } catch (_) { /* no answer is not news: the engine restarts, the tab sleeps */ }
}

function _armDownloadPoll(s) {
  const downloading = !!(s.browser && s.browser.state === "downloading");
  if (!downloading) { if (_fast) { clearTimeout(_fast); _fast = null; } return; }
  if (_fast) return;                         // one timer at a time, however many answers arrive
  _fast = setTimeout(() => { _fast = null; if (!document.hidden) check(); }, DOWNLOAD_POLL_MS);
}

// What the dot is coloured by. Deliberately NOT a fourth opinion: the engine computed `state` in
// `daemon_api.py` so that "running but no folders chosen is a warning" is decided once, and this returns
// the neutral value until the first answer arrives instead of flashing an alarm on every page load.
//
// The one place it adds to the engine's `state`: a cloud engine answers `remote`, and once the relay is
// connected that remote engine DOES reach this computer — green, the same as a local daemon that answers.
export function iconState() {
  const s = status();
  if (!s) return "unknown";
  if (s.state === "remote") return relayConnected() ? "ok" : "remote";
  return s.state || "off";
}

// The relay half of the status (`relay: {paired, connected, caps, version, platform, since}`). Absent on an engine
// without the relay — which is a fact about this engine, not a fault, and every reader treats it as "not here".
export function relay() { const s = status(); return (s && s.relay && typeof s.relay === "object") ? s.relay : null; }
export function relayConnected() { const r = relay(); return !!(r && r.connected); }

// The outbound tunnel (V2-836): `{capable, enabled, connected, hosts_last_hour}`, or null when the engine does not say.
export function egress() { const s = status(); return (s && s.egress && typeof s.egress === "object") ? s.egress : null; }

// Flip the tunnel switch on the daemon of THIS computer. ON always carries `consent: true`: it is only ever called
// from the «I understand, turn it on» button, after the consent text. Re-reads the status either way.
export async function setEgress(enabled) {
  let body = {};
  try {
    const r = await fetch("/api/daemon/egress", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ enabled: !!enabled, consent: !!enabled }) });
    try { body = await r.json(); } catch (_) { body = {}; }
  } catch (_) { body = {}; }
  await check();
  return body;
}

// The browser the daemon's sign-in window uses (`browser: {state, channel, progress, size_mb}`), or null when
// this daemon does not say — an older daemon, or none at all.
export function browser() { const s = status(); return (s && s.browser && typeof s.browser === "object") ? s.browser : null; }

// Download progress as a whole percent. The daemon may report a 0–1 fraction or a 0–100 percent; anything else
// (missing, negative, NaN) is "not known", which the screen draws as an indeterminate bar rather than as 0 %.
export function downloadPercent(b) {
  const p = Number(b && b.progress);
  if (!Number.isFinite(p) || p < 0) return null;
  return Math.min(100, Math.round(p <= 1 && !Number.isInteger(p) ? p * 100 : p));
}

// The browser state as ONE i18n key and its values — read by the desktop card and by the phone row, so the two
// can never word the same state differently.
export function browserLine() {
  const b = browser();
  if (!b) return { key: "daemon.browser.unknown", vars: null };
  if (b.state === "ready") return { key: b.channel === "chromium" ? "daemon.browser.ready_chromium" : "daemon.browser.ready_chrome", vars: null };
  if (b.state === "downloading") {
    const pct = downloadPercent(b);
    const mb = Number(b.size_mb);
    if (pct == null) return { key: "daemon.browser.downloading", vars: null };
    return Number.isFinite(mb) && mb > 0
      ? { key: "daemon.browser.downloading_pct_mb", vars: { pct, mb: Math.round(mb) } }
      : { key: "daemon.browser.downloading_pct", vars: { pct } };
  }
  if (b.state === "absent") return { key: "daemon.browser.absent", vars: null };
  if (b.state === "unsupported") return { key: "daemon.browser.unsupported", vars: null };
  return { key: "daemon.browser.unknown", vars: null };
}

// The connection as ONE i18n key: this computer over loopback, the cloud agent over the relay, or neither.
export function linkLine() {
  const s = status();
  if (!s) return { key: "daemon.link.unknown", vars: null };
  const r = relay();
  if (r && r.connected) return r.since ? { key: "daemon.link.relay_since", vars: { since: sinceText(r.since) } }
                                       : { key: "daemon.link.relay", vars: null };
  if (s.state !== "remote") return { key: s.reachable ? "daemon.link.local" : "daemon.link.none", vars: null };
  if (r && r.paired) return { key: "daemon.link.relay_offline", vars: null };
  return { key: r ? "daemon.link.unpaired" : "daemon.link.unknown", vars: null };
}

// `since` may be an ISO string or epoch seconds/ms. Shown in the viewer's own locale; unreadable → as given.
export function sinceText(v) {
  const n = typeof v === "number" ? (v < 1e12 ? v * 1000 : v) : Date.parse(v);
  if (!Number.isFinite(n)) return String(v || "");
  try { return new Date(n).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
  catch (_) { return new Date(n).toISOString(); }
}

// Pairing (V2-575 P3). A hosted engine mints a one-time code `{code, expires_at}` the daemon on his computer is
// given; over loopback there is nothing to pair (`{paired, mode: "loopback"}`); an engine without the relay says
// `relay_not_available`. Normalised to one of those three, plus the failure the screen shows as a problem.
export async function pair() {
  let body = {};
  try {
    const r = await fetch("/api/daemon/pair", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    try { body = await r.json(); } catch (_) { body = {}; }
  } catch (_) { return { ok: false, error: "" }; }
  if (body.error === "relay_not_available") return { ok: false, unavailable: true };
  if (!body.ok) return { ok: false, error: body.error || body.message || "" };
  if (body.mode === "loopback") return { ok: true, loopback: true };
  if (!body.code) return { ok: false, error: "" };
  return { ok: true, code: String(body.code), expiresAt: expiryMs(body.expires_at) };
}

// `expires_at` as epoch ms: an ISO string, epoch seconds or epoch ms. Unreadable → null (no countdown is drawn).
export function expiryMs(v) {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? (v < 1e12 ? v * 1000 : v) : Date.parse(v);
  return Number.isFinite(n) ? n : null;
}

// Offered on every engine once the first status has arrived. On a cloud account (`remote`) it is where the user
// gets the installer, and the setup screen says plainly what it can and cannot reach from there.
export function isOffered() { return !!status(); }
export function isRemote() { const s = status(); return !!s && s.state === "remote"; }
export function isConnected() { const s = status(); return !!s && !!s.reachable; }

// The installer for THIS visitor's machine, chosen by the engine from their user-agent — which is the right
// source and not `navigator.platform`: on a cloud account the engine's own platform is a Linux container,
// and a self-hoster may well be browsing from a second computer.
export function downloadFor(platform) {
  const s = status();
  if (!s || !s.downloads || !s.downloads.platforms) return null;
  const key = platform || s.platform || "";
  return s.downloads.platforms[key] || null;
}

export function platforms() {
  const s = status();
  return (s && s.downloads && s.downloads.platforms) ? s.downloads.platforms : {};
}

async function _permissions(action, path) {
  const r = await fetch(`/api/daemon/permissions/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  let body = {};
  try { body = await r.json(); } catch (_) { /* a 500 with no body is still a refusal */ }
  // The daemon's own sentence travels all the way here on purpose — it names the boundary ("that is your
  // entire home folder") and replacing it with a generic failure would leave the user with nothing to act on.
  if (!r.ok || !body.ok) return { ok: false, message: body.message || body.error || "" };
  await check();
  return { ok: true, roots: body.roots || [] };
}

export const grant  = (path) => _permissions("grant", path);

// The system's own folder dialog, opened by the daemon on this desktop. A cancel is not an error.
export async function pick(prompt) {
  let body = {};
  try {
    const r = await fetch("/api/daemon/permissions/pick", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }),
    });
    body = await r.json();
  } catch (_) { return { ok: false, message: "" }; }
  if (body.cancelled) return { ok: true, cancelled: true };
  if (!body.ok) return { ok: false, message: body.message || body.error || "" };
  await check();
  return { ok: true, roots: body.roots || [] };
}

// «Conectar»: the engine starts the daemon it carries; the screen then watches for it to answer (≤ 20 s).
export async function connect() {
  let body = {};
  try {
    const r = await fetch("/api/daemon/start", { method: "POST" });
    body = await r.json();
  } catch (_) { return { ok: false, message: "" }; }
  if (!body.ok) return { ok: false, message: body.message || body.error || "" };
  for (let i = 0; i < 20; i++) {
    await check();
    if (isConnected()) return { ok: true };
    await new Promise((res) => setTimeout(res, 1000));
  }
  return { ok: false, message: "start_timeout" };
}
export const revoke = (path) => _permissions("revoke", path);

export function start() {
  if (_iv) return;
  check();
  _iv = setInterval(() => { if (!document.hidden && !asleep()) check(); }, POLL_MS);   // V2-872: nor a sleeping tab
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
}

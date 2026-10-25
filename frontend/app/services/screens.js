// ============================================================================
// screens.js — this screen's side of «one agent, one voice, many screens» (V2-792).
//
// The server knows which screens are open and stamps every event with the screen that asked
// (`voice/screens.py`); `event-scope.js` says which events that stamp governs. This module is what a screen DOES
// with an event that belongs to another one, and the few things a screen tells the server about itself:
//
//   · a card opened on the other screen → a passive CHIP here («📄 Informe · on the computer — Open here»),
//     never the card itself. A result that grabs this screen in the middle of something else is the failure
//     this initiative removes; one tap brings it.
//   · a card that takes the device's sound or picture (manifest `"screens": "single"`: video, music) lives on ONE
//     screen. Asking for it on another screen moves it — the server announces the move the moment the order lands
//     (`voice/screens.py`), opening it here by hand tells the server (`/api/screens/bring`) — and every other screen
//     lets it go and keeps a «▶ now on the phone — Bring here» chip. A `"shared"` card (a calendar, a list) is a
//     reflection and may be open everywhere. The policy is the widget's own (`widgets/screen_policy.py`).
//   · visible / hidden / touched, so the server can tell the active screen.
//
// Shared by both shells: the desktop canvas and the phone deck expose the same host contract (show/close/list).
// ============================================================================
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";
import { surfaceOf } from "./event-scope.js?v=1";

const MAX_CHIPS = 3;
const CHIP_TTL_MS = 15 * 60 * 1000;

const base = (id) => String(id || "").split("::", 1)[0].trim().toLowerCase();

// The catalogue's `screens` policy, read once from the compact index (both hosts load it lazily, so a deck being
// restored may not have it yet — this does not depend on that).
let _oneScreen = null, _names = {};
async function oneScreenIds() {
  if (_oneScreen) return _oneScreen;
  try {
    const r = await fetch("/widgets", { cache: "no-store" }).then((x) => x.json());
    const rows = Array.isArray(r) ? r : (r && (r.widgets || r.items)) || [];
    _oneScreen = new Set(rows.filter((w) => w && w.screens === "single").map((w) => String(w.id)));
    for (const w of rows) if (w && w.id) _names[String(w.id)] = w.name || w.title || "";
  } catch (_) { return new Set(); }
  return _oneScreen;
}
export async function isOneScreen(id) { return (await oneScreenIds()).has(base(id)); }

function cardName(host, id) {
  const m = host && host._meta && host._meta[base(id)];
  return (m && (m.name || m.title)) || _names[base(id)] || base(id);
}

function push(chip) {
  const now = Date.now();
  const keep = store.elsewhere().filter((c) => c.key !== chip.key && now - c.at < CHIP_TTL_MS);
  store.setElsewhere([{ ...chip, at: now }, ...keep].slice(0, MAX_CHIPS));
}
export function dismiss(key) { store.setElsewhere(store.elsewhere().filter((c) => c.key !== key)); }

/** An origin-scoped event for another screen arrived. Only `show` leaves a chip: a fullscreen, a move or a panel
 *  on the other screen is that screen's business and says nothing worth a tap here. */
export function noteElsewhere(host, d) {
  if (!(d && d.kind === "widget" && d.label === "show" && d.id) || d.src === "user") return;
  isOneScreen(d.id).then((one) => push({
    key: "show:" + d.id, id: d.id, dev: d.origin_dev, why: one ? "playing" : "opened",
    name: cardName(host, d.id), data: d.data || null,
  }));
}

/** `screens/moved`: a one-screen card was brought to `d.to`. Every other screen that has it open lets it go. */
export function onMoved(host, d) {
  if (!d || !d.id || d.to === api.DEVICE) { if (d && d.id) dismiss("show:" + d.id); return; }
  const open = (host && host.list ? host.list() : []).filter((x) => base(x) === base(d.id));
  if (!open.length) return;
  for (const x of open) { try { host.close(x); } catch (_) {} }
  oneScreenIds().then(() => push({ key: "show:" + d.id, id: d.id, dev: d.to, why: "moved", name: cardName(host, d.id) }));
}

/** One tap: open the card on THIS screen, and if it plays, take it from the others. */
export async function bringHere(host, chip) {
  dismiss(chip.key);
  try { await host.show(chip.id, chip.data ? { data: chip.data } : {}); } catch (_) {}
  if (await isOneScreen(chip.id)) api.screensBring(chip.id);
  api.screensBeat(true, true);
}

/** A screen being RESTORED (page load) leaves out the cards that play on one screen and are open on another one
 *  right now, and says so with a chip. Without this the phone, opened while the desktop played a video, restored
 *  the same video from the account's layout and started it a second time. */
export async function filterRestore(host, items, srv) {
  const there = new Map(((srv && srv.elsewhere) || []).map((x) => [base(x.id), x.dev]));
  if (!there.size) return items;
  const one = await oneScreenIds();
  return items.filter((it) => {
    const b = base(it && it.id);
    if (!one.has(b) || !there.has(b)) return true;
    push({ key: "show:" + it.id, id: it.id, dev: there.get(b), why: "playing", name: cardName(host, it.id) });
    return false;
  });
}

/** Opening a one-screen card by hand here (catalogue, deep link) moves it here too. Called by the hosts. */
export async function claimIfOneScreen(id) {
  if (await isOneScreen(id)) api.screensBring(id);
}

/** The words for a chip, given the i18n `t`. Kept here so both shells say the same thing. */
export function chipText(t, chip) {
  const where = t("screens.on_" + (surfaceOf(chip.dev) || "other"));
  const line = chip.why === "playing" ? t("screens.playing_there", { name: chip.name, where })
             : chip.why === "moved" ? t("screens.moved_there", { name: chip.name, where })
             : t("screens.opened_there", { name: chip.name, where });
  const action = chip.why === "opened" ? t("screens.open_here") : t("screens.bring_here");
  return { line, action };
}

// Visible / hidden / touched → the server's registry. A touch is throttled: it marks the ACTIVE screen, and one
// per 20 s is all that needs.
let _touchAt = 0;
export function wireScreen() {
  try {
    document.addEventListener("visibilitychange", () => api.screensBeat(!document.hidden));
    window.addEventListener("pointerdown", () => {
      const now = Date.now();
      if (now - _touchAt < 20000) return;
      _touchAt = now;
      api.screensBeat(true, true);
    }, { passive: true });
    api.screensBeat(!document.hidden);
  } catch (_) {}
}

// ============================================================================
// desktop-screen.js — the windowed desk's ADAPTER for its one screen document (V2-907 T7, §3.1).
//
// Read from the desk as it is drawn, never from what was asked of it:
//   · layer — z order, top first (`style.zIndex`, the one `_bringFront` writes; then the time it last came forward);
//   · vis   — `min` for a card in the rail (`hb-minned`), `front` for the top card on screen, `behind` for one a
//             maximised / full-screen card covers or another card covers whole, else `visible`; the activity rail's
//             card above the orb is always `visible`;
//   · flags — `max` while maximised in the app (`_restore` is its marker), `fs` while in the browser's full screen;
//   · a desk has no home: the bare desk is `front: ""`; `panel` is the native surface open over it (`screen-panel.js`).
// Every change the desk announces (`hb:canvas-changed`: a show, close, minimise, maximise, focus by his hand) is
// reported; `services/sse.js` answers each order through `screen-order.js`.
// ============================================================================
import { screenReporter, watchRestore } from "./screen-reporter.js?v=1";
import { panelOf, watchPanel, DESKTOP_PANELS } from "./screen-panel.js?v=1";

const _z = (c) => parseInt(c && c.style && c.style.zIndex, 10) || 0;
const _covers = (a, b) => a.left <= b.left + 1 && a.top <= b.top + 1 && a.right >= b.right - 1 && a.bottom >= b.bottom - 1;

export function desktopAdapter(desk) {
  const card = (id) => { const w = desk.wins.get(id); return w && w.card; };
  const stack = () => [...desk.wins.keys()].filter((id) => card(id))
    .sort((x, y) => (_z(card(y)) - _z(card(x))) || ((card(y)._t || 0) - (card(x)._t || 0)));
  const full = (c) => !!c && (c._restore || document.fullscreenElement === c
    || c.classList.contains("hb-cinema") || c.classList.contains("hb-fullwide"));
  const vis = (id) => {
    if (desk._actId === id && !desk.wins.has(id)) return "visible";
    const c = card(id);
    if (!c) return "";
    if (c.classList.contains("hb-minned")) return "min";
    const shown = stack().filter((x) => !card(x).classList.contains("hb-minned"));
    const k = shown.indexOf(id);
    if (k === 0) return "front";
    const above = shown.slice(0, k).map(card);
    if (above.some(full)) return "behind";
    const r = c.getBoundingClientRect();
    return above.some((o) => _covers(o.getBoundingClientRect(), r)) ? "behind" : "visible";
  };
  return {
    layout: "windows",
    list: () => [...stack(), ...(desk._actId && !desk.wins.has(desk._actId) ? [desk._actId] : [])],
    vis,
    layer: (id) => { const k = stack().indexOf(id); return k >= 0 ? k : desk.wins.size; },
    flags: (id) => { const c = card(id); return { max: !!(c && c._restore), fs: !!c && document.fullscreenElement === c }; },
    home: () => ({ shown: false, holds: [] }),
    panel: () => panelOf(DESKTOP_PANELS),
  };
}

// The desk's one screen: `{adapter, rep}`, reporting every change the desk announces.
export function desktopScreen(desk, opts = {}) {
  const adapter = desktopAdapter(desk);
  const rep = screenReporter(adapter, { device: opts.device || (() => import("../services/api.js?v=2").then((m) => m.DEVICE)), ...opts });
  const cause = () => { const by = Object.values(desk._by || {}); return by.includes("hand") ? "hand" : by[0] || ""; };
  try { document.addEventListener("hb:canvas-changed", () => rep.changed(cause())); } catch (_) {}
  watchPanel(DESKTOP_PANELS, () => rep.changed());   // a panel opened or closed over the canvas (T9)
  adapter.restoring = watchRestore(desk, () => rep.changed("restore"));   // a reload: unknown until restored
  return { adapter, rep };
}

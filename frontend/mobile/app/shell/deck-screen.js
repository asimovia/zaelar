// ============================================================================
// deck-screen.js — the phone deck's ADAPTER for its one screen document (V2-907 T8, §3.1).
//
// A deck shows one app at a time: the card on screen (`order[at]`) is `front`, every other open card is `behind`
// (a deck never reports `visible`), layer 0 is the front and the rest follow the deck's order. At `at = -1` the
// HOME is on screen and nothing is in front (`front: ""`); the home says what it holds by declared names — the
// lines `HomeToday` drew (greeting, next_events, now_playing) and the tiles of the open apps (`apps`).
// The deck reports through the shared `widgets/screen-reporter.js` on every `_reportOpen` (a show, close, page,
// home); `services/sse.js` answers each order through `widgets/screen-order.js`, as on the desktop.
// ============================================================================
import { screenReporter, watchRestore } from "../../../app/widgets/screen-reporter.js?v=1";
import { panelOf, pagePanels, watchPanel } from "../../../app/widgets/screen-panel.js?v=1";

// The page open over the deck (V2-907 T9). `pages.js` is read once the shell has loaded: it imports the apps page,
// which reaches this module through the deck, so a static import would read it mid-evaluation.
let PANELS = [];

export function deckAdapter(deck) {
  const front = () => (deck.at >= 0 ? deck.order[deck.at] || "" : "");
  const rest = () => deck.order.filter((id) => id !== front());
  return {
    layout: "deck",
    list: () => [...deck.order],
    vis: (id) => (!deck.order.includes(id) ? "" : id === front() ? "front" : "behind"),
    layer: (id) => (id === front() ? 0 : rest().indexOf(id) + (front() ? 1 : 0)),
    home: () => ({ shown: deck.at === -1,
                   holds: [...((deck._today && deck._today.holds && deck._today.holds()) || []), ...(deck.order.length ? ["apps"] : [])] }),
    panel: () => panelOf(PANELS),
  };
}

// The deck's one screen: `{adapter, rep, changed()}`.
export function deckScreen(deck, opts = {}) {
  const adapter = deckAdapter(deck);
  const rep = screenReporter(adapter, { device: opts.device || (() => import("../../../app/services/api.js?v=2").then((m) => m.DEVICE)), ...opts });
  import("./pages.js?v=1").then((m) => { PANELS = pagePanels(m.PAGES); watchPanel(PANELS, () => rep.changed()); rep.changed(); })
    .catch(() => {});
  const changed = () => { const by = Object.values(deck._by || {}); rep.changed(by.includes("hand") ? "hand" : by[0] || ""); };
  adapter.restoring = watchRestore(deck, () => rep.changed("restore"));   // a reload: unknown until restored
  return { adapter, rep, changed };
}

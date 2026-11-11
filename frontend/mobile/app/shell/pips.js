// pips.js — the deck's PAGE SWITCHER (V2-876 D-B, P-15, P-17): the row above the dock, one pip for the home and one per
// open app, the current one lit, a producing one glowing. It is a control two ways: a TAP on a pip goes there, and a
// finger DRAGGED along the row moves through the pages under it (the platform's page-control scrub). The deck's own
// swipe never starts on this row (Deck.js lists `.zm-pips` among what owns a sideways drag). More than MAX apps
// collapse into a window of MAX around the current one plus a «k/n» counter — never a row of seven dots. The row is
// its own band between the card and the dock (styles.css), so it is never painted inside a card's frame.
import { t } from "../../../app/core/i18n.js?v=1";

const MAX = 5;

/** Repaint the row for `deck` (its order, its position, what produces). */
export function paintPips(deck, row, homeIco) {
  const n = deck.order.length;
  deck.stage.classList.toggle("has-pips", n >= 1);
  const from = n <= MAX ? 0 : Math.max(0, Math.min(n - MAX, deck.at - Math.floor(MAX / 2)));
  const ks = [-1]; for (let k = from; k < Math.min(n, from + MAX); k++) ks.push(k);
  // The SAME buttons while the set is the same: a finger scrubbing the row holds the pip it went down on, and a
  // rebuilt row would leave its touch events on a detached node.
  const key = n < 1 ? "" : deck.order.join("|") + "@" + from;
  if (row.dataset.key !== key) {
    row.dataset.key = key;
    row.replaceChildren(...(n < 1 ? [] : ks.map((k) => {
      const b = document.createElement("button");
      b.dataset.k = String(k);
      b.onclick = () => (k < 0 ? deck.home() : deck._goTo(k, 0));
      if (k < 0) { b.innerHTML = homeIco; b.setAttribute("aria-label", t("mobile.home")); }
      return b;
    })));
    if (n > MAX) row.append(Object.assign(document.createElement("span"), { className: "zm-pipn" }));
  }
  for (const b of row.querySelectorAll(".zm-pip, button")) {
    const k = Number(b.dataset.k), w = k >= 0 && deck.cards.get(deck.order[k]);
    b.className = "zm-pip" + (k < 0 ? " home" : "") + (w && deck._producing(w) ? " prod" : "") + (k === deck.at ? " on" : "");
    if (k >= 0) b.setAttribute("aria-label", (w && w.titleEl.textContent) || deck.order[k]);
  }
  const c = row.querySelector(".zm-pipn");
  if (c) c.textContent = (deck.at >= 0 ? deck.at + 1 : 0) + "/" + n;
}

/** The scrub: a finger that goes down on the row and slides goes to the page under it, once per pip crossed. */
export function wirePipDrag(deck, row) {
  let on = false;
  const under = (x, y) => {
    const el = document.elementFromPoint(x, y);
    const b = el && el.closest && el.closest(".zm-pip");
    return b && row.contains(b) ? Number(b.dataset.k) : null;
  };
  row.addEventListener("touchstart", () => { on = true; }, { passive: true });
  row.addEventListener("touchmove", (e) => {
    if (!on || !e.touches[0]) return;
    const k = under(e.touches[0].clientX, e.touches[0].clientY);
    if (k !== null && k !== deck.at) (k < 0 ? deck.home() : deck._goTo(k, 0));
  }, { passive: true });
  row.addEventListener("touchend", () => { on = false; }, { passive: true });
  row.addEventListener("touchcancel", () => { on = false; }, { passive: true });
}

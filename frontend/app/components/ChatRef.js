// ============================================================================
// ChatRef.js — an errand's REFERENCE BOX in the conversation (V2-862).
//
// A worker's deliverable (a report, a results sheet, pictures, a card it built) goes to its own card, not into the
// chat. Before this, closing that card left nothing in the thread to say it had ever existed. The engine now emits
// one `artifact` event per errand (`nucleo/chat_refs.py`) and the store keeps ONE row per task (`upsertChatRef`);
// this file only DRAWS that row, for both shells — the desktop wall and the phone's chat sheet render the same
// `chatMsgs()` and must not draw two different boxes.
//
// Clicking reopens through the existing door: `POST /api/tasks/reopen` rebuilds the deliverable from what the task
// kept and answers with the card instance, which opens through `hb:open-card` like every other click. While the
// errand is still running its card is live, so the box opens that card directly when the door has nothing yet.
// ============================================================================

import { h } from "../core/dom.js?v=2";
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";

//: The glyph per surface (`nucleo/surfaces.py`). A surface not listed here still draws, with the generic one.
const GLYPH = { informe: "📄", lista: "🗂", item: "🗂", imagenes: "🖼", widget: "🧩" };

const openCard = (id) => {
  if (!id) return false;
  try { document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id } })); } catch (_) { return false; }
  return true;
};

async function reopen(m, el) {
  const r = await api.taskReopen(m.ref);
  if (r && r.ok && r.instance && openCard(r.instance)) return;
  if (openCard(m.card)) return;
  // Nothing was kept and no card is known: the box says so instead of opening a blank card.
  if (!el) return;
  el.classList.add("hb-ref--gone");
  const st = el.querySelector(".hb-ref-state");
  if (st) st.textContent = t("chat.ref.gone");
}

/** The row for one `{role: "ref"}` message. `cls` is the host's own row class (desktop `cw-msg`, phone `zm-msg`). */
export function chatRefView(m, cls = "cw-msg") {
  const state = ["done", "partial", "cancelled"].includes(m.state) ? m.state : "started";
  const el = h("button", {
    type: "button", class: `${cls} ref hb-ref hb-ref--${state}`, "data-ref": m.ref, "data-surface": m.surface || "",
    title: () => t("chat.ref.open"),
    onClick: () => reopen(m, el),
  },
    h("span", { class: "hb-ref-glyph", "aria-hidden": "true" }, GLYPH[m.surface] || "📎"),
    h("span", { class: "hb-ref-main" },
      h("span", { class: "hb-ref-title" }, m.text || (() => t("chat.ref.untitled"))),
      h("span", { class: "hb-ref-state" }, () => t("chat.ref." + state)
        + (m.file ? " · " + String(m.file).split("/").pop() : "")),
    ),
    h("span", { class: "hb-ref-go", "aria-hidden": "true" }, "↗"),
  );
  return el;
}

// ChatSheet.js — the chat on the phone. Mobile counterpart of components/ChatWall.js; the SHELL is new, the CONTENT is
// not forked: the rows are store.chatMsgs() (the desktop wall's signal) and sending is ChatWall's submitChat(), the ONE
// path from a typed sentence to the agent — a local copy would be a second path, and a second path is how one shell
// starts recording messages the other never sees. One tab only: processes and crons live in the menu, clusters are
// desktop setup; `store.chatTab` is left alone so the phone never changes what the desktop shows.
import { h, raw } from "../../../app/core/dom.js?v=2";
import { createEffect, createSignal } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { submitChat } from "../../../app/components/ChatWall.js?v=5";
import { chatRefView } from "../../../app/components/ChatRef.js?v=1";
import { renderMarkdownLite } from "../../../app/lib/markdown-lite.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";
import * as consent from "./ai-consent.js?v=1";

const SEND = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`;

export function ChatSheet() {
  let listEl = null, inputEl = null, stick = true;
  const [offNote, setOffNote] = createSignal(false);   // a line sent with ⏻ off says nobody will answer (V2-877 #10)
  createEffect(() => { if (!store.powerOff()) setOffNote(false); });

  const send = () => {
    const v = (inputEl && inputEl.value) || "";
    if (!v.trim()) return;
    if (consent.pending()) { consent.setSheetOpen(true); return; }   // V2-870: in the app a line asks first
    stick = true;                       // his own line always brings the list down to it
    submitChat(v);
    inputEl.value = "";
    if (store.powerOff()) setOffNote(true);
    // Keep the keyboard up: on a phone, dismissing it after every line turns a conversation into a chore.
    inputEl.focus();
  };

  const sheet = h("section", {
    class: () => "zm-sheet zm-chat" + (store.chatOpen() ? " open" : ""),
    "aria-hidden": () => (store.chatOpen() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("h2", null, () => t("chat.title")),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"), onClick: () => store.setChatOpen(false) }, "×"),
    ),
    h("div", { class: "zm-msgs", ref: (el) => (listEl = el),
      // Following the newest line is a STATE of the list, read from his last scroll — measured after a render it
      // is already wrong (the new line made the list taller), which is why the list never followed (V2-877 #10).
      onScroll: () => { stick = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 120; } },
      // The chat is the conversation, not a log (V2-876 rule 6): a voice filler is a sound, never a bubble.
      () => store.chatMsgs().filter((m) => m.kind !== "filler").map((m) => {
        if (m.role === "ref") return chatRefView(m, "zm-msg");   // V2-862: the same box the desktop wall draws
        const row = h("div", { class: "zm-msg " + (m.role || "sys") });
        // The agent speaks markdown (lists, bold, code); the person does not. Same renderer as the desktop wall.
        if (m.role === "agent") row.innerHTML = renderMarkdownLite(m.text || "");
        else row.textContent = m.text || "";
        return row;
      }),
      () => (offNote() ? h("div", { class: "zm-msg sys zm-off-note" }, t("mobile.chat_off")) : null),
    ),
    h("form", { class: "zm-compose", onSubmit: (e) => { e.preventDefault(); send(); } },
      h("input", {
        ref: (el) => (inputEl = el),
        type: "text", autocomplete: "off", autocapitalize: "sentences", enterkeyhint: "send",
        placeholder: () => t("chat.placeholder"),
      }),
      h("button", { type: "submit", class: "zm-send", "aria-label": () => t("chat.send") }, raw(SEND)),
    ),
  );

  // Opening the chat lands on the newest line; a new line follows him down unless he scrolled up to read.
  const down = () => { if (listEl && stick) requestAnimationFrame(() => { listEl.scrollTop = listEl.scrollHeight; }); };
  createEffect(() => { if (store.chatOpen()) { stick = true; down(); } });
  createEffect(() => { store.chatMsgs(); offNote(); down(); });

  return sheet;
}

// ChatWall — vertical agent panel with FIVE tabs (grown from three at V2-079): “Chat” (write to the agent),
// “Processes” (live Brain Workers + history of what ran today/yesterday/a few days ago), “Crons” (scheduled
// tasks), “Clusters” (V2-086, the native MeshKore network), and “Conectores” (V2-561/V2-526, every connector
// by category — built + wishlist). Toggled by store.chatOpen; the active tab lives in store.chatTab (so the
// orb’s ⏰ button can open it directly on “Crons”). Chat goes through session.sendText → data channel →
// ClientTextInjector (normal user turn; the agent responds by voice). “Processes”/“Crons”/“Clusters”/
// “Conectores” give the operator PERSPECTIVE and REACH beyond conversation (the hexagons are the "now";
// this panel is "now + history + the rest of the system").
//
// WINDOW BEHAVIOUR (V2-062): MOVABLE (drag by the header) + RESIZABLE from ANAnd edge/corner (8 handles, lib/
// resizable.js) + DOCKABLE: drag it to the far left/right edge and it snaps to a FULL-HEIGHT side column. Floating
// geometry persists under FLOAT_KEY; the docked side+width under DOCK_KEY.
//
// A Ctrl+V anywhere on the page (see main.js) ALSO feeds the chat channel — pasted text reaches the agent even
// while this panel is hidden; it shows up here the next time you open it.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import * as chatFiles from "../services/chat-files.js?v=1";
import { makeResizable } from "../lib/resizable.js?v=1";
import { mountClusters } from "../services/clusters-bridge.js?v=1";
import { CLOSE_ICON, PAPERCLIP_ICON, MESSAGE_SQUARE_ICON, ACTIVITY_ICON, CLOCK_ICON, SERVER_ICON, LINK_ICON, APPS_ICON, WIDGETS_ICON } from "../lib/icons.js?v=1";
import { renderMarkdownLite } from "../lib/markdown-lite.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { mountProcesos } from "../services/procesos-bridge.js?v=1";
import { AskWall, anchoredAsks, askBox } from "./TaskAsk.js?v=2";
import { chatRefView } from "./ChatRef.js?v=1";
import * as a2a from "./A2AView.js?v=1";
import { onCardFront } from "../widgets/card-front.js?v=1";
import { mountAppsTab } from "../services/apps-bridge.js?v=1";
import { mountConectores } from "../services/conectores-bridge.js?v=1";
import * as red from "../services/red-bridge.js?v=1";
import { createWallBridge, submitLine } from "../services/wall-bridge.js?v=1";
import { createWallStorage, CAP as WALL_CAP } from "../services/wall-storage.js?v=1";
import { legacy, MAX_TEXT } from "../services/wall-legacy.js?v=1";

const SEND_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`;
// V2-621 — the ONE map from a tab id to its label key: the header's standing name (`.cw-tabname`) and each
// tab button's own label read the same entry, so they cannot drift apart.
const TAB_LABEL = { chat: "chat.tabChat", procesos: "chat.tabTasks",
                    clusters: "chat.tabClusters", red: "a2a.network", conectores: "chat.tabConnectors", apps: "chat.tabApps" };
const FLOAT_KEY = "hb_chat_float", DOCK_KEY = "hb_chat_dock", OPEN_KEY = "hb_chat_open";

// WHETHER IT WAS OPEN survives a reload too (V2-550). Its GEOMETRY already did — floating rect under
// FLOAT_KEY, docked side+width under DOCK_KEY — so the operator's report («refresh and the chat wall does not
// stay where it was») was precise in a way worth keeping: the position was never the part that was lost. The
// panel simply came back CLOSED, every time, because `store.chatOpen` is a signal born `false`, and reopening
// it then restored the geometry correctly — which is why it looked like the position was fine but the window
// «moved». Canvas cards have persisted open+position since the beginning; this is the one surface on the
// desktop that did not, and it is the one he keeps open all day.
//
// The TAB travels with it: coming back to a panel he had left on «Procesos» and finding «Chat» is the same
// loss one level down. Kept in localStorage next to the geometry it belongs with, not in the canvas layout —
// this is a native panel, not a card, and splitting one window's state across two stores is how they drift.
function loadOpen() {
  try {
    const s = JSON.parse(localStorage.getItem(OPEN_KEY) || "null");
    if (s && typeof s === "object") return { open: !!s.open, tab: String(s.tab || "chat") };
  } catch (_) {}
  return { open: false, tab: "chat" };
}

function saveOpen() {
  try { localStorage.setItem(OPEN_KEY, JSON.stringify({ open: !!store.chatOpen(), tab: store.chatTab() })); }
  catch (_) {}
}

// A server-side wipe («reset») must reach this too: `desktop.restore()` owns the wipe epoch and calls this, so
// a blank desktop is genuinely blank instead of one panel that outlived the reset.
export function forgetChatPlacement() {
  try { localStorage.removeItem(OPEN_KEY); } catch (_) {}
  store.setChatOpen(false);
}
const DOCK_PX = 34, MIN_W = 260, MIN_H = 200, DOCK_MIN_W = 280, DOCK_DEF_W = 340;

const _num = (v, d) => (typeof v === "number" && isFinite(v) ? v : d);
function loadFloat() {
  try { const s = JSON.parse(localStorage.getItem(FLOAT_KEY) || "null"); if (s && s.w && s.h) return s; } catch (_) {}
  return null;
}
function loadDock() {
  try { const d = JSON.parse(localStorage.getItem(DOCK_KEY) || "null"); if (d && (d.side === "left" || d.side === "right")) return d; } catch (_) {}
  return null;
}

// Send a message both to the agent and to the on-screen log. Used by the input AND by the paste handler.
// V2-809 — `atts` are REFERENCES to files already uploaded through the upload door ({id, name, kind, size,
// thumb}); the bytes never ride the message. The server already holds them as the turn's state, so the line the
// agent receives is his text — or, for a message that is only files, their names.
export function submitChat(text, atts) {
  const t = (text || "").trim().slice(0, MAX_TEXT);
  const a = (atts || []).filter((x) => x && x.id);
  if (!t && !a.length) return;
  const said = t || a.map((x) => "📎 " + x.name).join("\n");
  const extra = a.length ? { kind: "att", data: { att: a, bare: !t } } : {};
  if (submitLine(said, extra) === null) session.sendText(said);   // no wall on this page: the line still goes out
}

// A line's body and classes on this wall — the look it always had (`cw-msg` and its role, markdown for ours, his
// attachments, a peer's header, the crawl of the line the voice is saying). The component draws the rest.
const ROLE_CLASS = { you: "you", agent: "agent", note: "sys" };
function lineClasses(l) {
  if (l.role === "box") return "";
  const role = l.role === "note" ? (l.kind === "record" ? "record" : l.kind === "peer" ? "peer" : "sys") : ROLE_CLASS[l.role] || "you";
  const speaking = l.role === "agent" && l.state === "live" && l.heard !== undefined && l.heard < l.text.length;
  return `cw-msg ${role}` + (l.state === "live" && l.role === "you" ? " cw-live" : "") + (speaking ? " cw-speaking" : "");
}
function lineBody(l, said) {
  const box = document.createDocumentFragment();
  const d = l.data || {};
  if (l.kind === "peer") {
    const who = d.dir === "out" ? `🛰 → ${d.peer || "?"}` : d.dir === "in" ? `🛰 ${d.peer || "?"}` : "🛰";
    box.appendChild(h("div", { class: "cw-msg-from" }, d.cluster && d.dir ? `${who} · ${d.cluster}` : who));
  }
  const plain = l.state !== "final" || (l.role === "agent" && said !== l.text);   // half-said: never markdown
  if (said && !d.bare) box.appendChild(plain ? h("div", { class: "cw-msg-body" }, said)
                                             : raw(`<div class="cw-msg-body">${renderMarkdownLite(said)}</div>`));
  if (Array.isArray(d.att) && d.att.length) box.appendChild(h("div", { class: "cw-msg-att" }, ...d.att.map(attView)));
  return box;
}
const KIND_GLYPH = { image: "🖼", pdf: "📄", text: "📝" };
const ACCEPT = "image/png,image/jpeg,image/gif,image/webp,application/pdf,.pdf,.txt,.md,.markdown,.csv,text/plain,text/csv,text/markdown";

// An attachment as the chat log shows it — in the bubble, and again in a restored history (the thumbnail is a
// URL of the engine, not bytes in the log).
function attView(a) {
  if (a.thumb) return h("img", { class: "cw-att-img", src: a.thumb, alt: a.name, title: a.name, decoding: "async" });
  return h("div", { class: "cw-att-file", title: a.name },
    h("span", { class: "cw-att-glyph" }, KIND_GLYPH[a.kind] || "📎"),
    h("span", { class: "cw-att-name" }, a.name),
    h("span", { class: "cw-att-size" }, chatFiles.fmtSize(a.size)));
}

// Auto-place like a widget: below the camera unit if it fits, else to its right, else overlapping (on top).
function placeWall(el) {
  const pad = 14, gap = 14, me = document.querySelector("#me");
  const r = me ? me.getBoundingClientRect() : { left: 18, right: 230, top: 16, bottom: 216 };
  const w = el.offsetWidth || 320, hh = el.offsetHeight || Math.min(innerHeight * 0.6, 520);
  const set = (x, y) => { el.style.right = "auto"; el.style.bottom = "auto"; el.style.left = Math.max(pad, x) + "px"; el.style.top = Math.max(pad, y) + "px"; };
  if (r.bottom + gap + hh <= innerHeight - pad) return set(r.left, r.bottom + gap);   // 1) below the camera
  if (r.right + gap + w <= innerWidth - pad) return set(r.right + gap, r.top);        // 2) beside it (right)
  set(Math.min(r.left, innerWidth - w - pad), r.top);                                 // 3) no room → on top
}

// Compact relative time for process history (finished_at in epoch seconds, like Python time.time()).
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - Number(ts));
  if (s < 60) return t("chat.agoNow");
  if (s < 3600) return t("chat.agoMinutes", { n: Math.floor(s / 60) });
  if (s < 86400) return t("chat.agoHours", { n: Math.floor(s / 3600) });
  const d = Math.floor(s / 86400);
  return d === 1 ? t("chat.agoYesterday") : t("chat.agoDays", { n: d });
}

export function ChatWall() {
  let listEl, inputEl, headEl, wallEl, previewEl = null;
  const [wallTraces, setWallTraces] = createSignal(legacy.traces());   // the turns on the wall (an ask's anchor)
  legacy.onChange(() => setWallTraces(legacy.traces()));
  let dockSide = null;                         // null | "left" | "right"
  let dockW = DOCK_DEF_W;                      // the docked column's INTENDED width (see setReserve)
  let lastDockSide = (loadDock() || {}).side || "left";   // where the ⧉ toggle docks a floating box (V2-621)
  let undockEl = null;                         // the box↔column MODE TOGGLE (visible in both shapes, V2-621)
  // `dockSide` is a plain variable a reactive binding would read exactly once (the V2-608 lesson) — this
  // SIGNAL mirrors it for the toggle's reactive title/glyph, written only by setReserve.
  const [isDocked, setIsDocked] = createSignal(false);
  let floatGeo = loadFloat();                  // {left,top,w,h} of the FLOATING window (last known)
  // Reopen exactly as it was left. Done HERE, at construction, so the first paint already has it: flipping the
  // signal later would show the desktop for a frame and then drop a panel on top of it.
  const _wasOpen = loadOpen();
  if (_wasOpen.open) { store.setChatTab(_wasOpen.tab); store.setChatOpen(true); }
  // A card brought to the front must be SEEN (card-front.js, 2026-11-16). The docked column reserves its own strip, so
  // it never covers a card; the FLOATING box does when it covers the screen (≤640 px it is a sheet over half the
  // canvas): then it folds away, as the phone's full-screen chat does. A small floating box beside the cards stays.
  onCardFront(() => {
    if (!store.chatOpen() || dockSide || !wallEl) return;
    const r = wallEl.getBoundingClientRect(), vw = window.innerWidth || 1, vh = window.innerHeight || 1;
    if ((r.width * r.height) / (vw * vh) >= 0.35) store.setChatOpen(false);
  });

  // V2-646 — NOTHING IS LISTENING, SO NOTHING IS SENT (operator, 2026-09-09): «estaba el agente parado y me
  // he puesto a escribir… si lo mando y nadie está escuchando se pierde». It did: `session.sendText` queues
  // the text and calls `start()`, but with the server's ⏻ OFF that start REFUSES (its own gate), so the
  // message sat in the pending queue forever while the wall showed it as sent and the composer was cleared —
  // he had to retype it from scratch. The composer now refuses in that ONE state («off»), keeps the text
  // where he wrote it, and says why. `starting` is NOT blocked: there the queue really does flush on connect.
  const canSend = () => store.agentState() !== "off";

  // ── ATTACHMENTS (V2-809) ───────────────────────────────────────────────────────────────────────────────
  // One row per file, each with its own fate: `up` (progress, cancellable), `reading`, `ready`, or `error` with
  // the sentence that says why — so one file of several failing never takes the others with it. A refusal the
  // limits can decide is said before anything travels; the server refuses again either way.
  const [pend, setPend] = createSignal([]);
  let fileEl = null, _attSeq = 0;
  const patchAtt = (key, p) => setPend((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x)));
  const forget = (x) => { if (x && x.local) { try { URL.revokeObjectURL(x.local); } catch (_) {} } };
  const removeAtt = (key) => {
    const x = pend().find((y) => y.key === key); if (!x) return;
    if (x.handle && (x.phase === "up" || x.phase === "reading")) x.handle.cancel();
    if (x.phase === "ready" && x.ref) chatFiles.detach(x.ref.episode_id);
    forget(x);
    setPend((xs) => xs.filter((y) => y.key !== key));
  };
  const attBusy = () => pend().some((x) => x.phase === "up" || x.phase === "reading");
  const addFiles = async (files) => {
    // Copied BEFORE the first await: an input's FileList is live, and the picker is reset right after this call.
    const list = Array.from(files || []);
    const L = await chatFiles.limits();
    for (const f of list) {
      const key = "a" + (++_attSeq), name = f.name || "archivo", kind = chatFiles.kindOf(f);
      const live = pend().filter((x) => x.phase !== "error");
      const sum = live.reduce((s, x) => s + (x.size || 0), 0);
      let note = "";
      if (!kind) note = t("chat.attachType", { name });
      else if (f.size > L.max_file_bytes) note = t("chat.attachTooLarge", { name, max: chatFiles.fmtSize(L.max_file_bytes) });
      else if (live.length >= L.max_files_per_message) note = t("chat.attachTooMany", { name, n: L.max_files_per_message });
      else if (sum + f.size > L.max_message_bytes) note = t("chat.attachMessageTooLarge", { name, max: chatFiles.fmtSize(L.max_message_bytes) });
      if (note) { setPend((xs) => [...xs, { key, name, kind, size: f.size, phase: "error", note }]); continue; }
      const handle = chatFiles.upload(f, { lim: L, onState: (st) => patchAtt(key, st) });
      const local = kind === "image" ? URL.createObjectURL(f) : null;
      setPend((xs) => [...xs, { key, name, kind, size: f.size, phase: "up", pct: 0, handle, local }]);
      handle.done.then((out) => {
        const still = pend().some((x) => x.key === key);
        if (!still) { if (out.ok) chatFiles.detach(out.ref.episode_id); return; }
        if (out.ok) return patchAtt(key, { phase: "ready", ref: out.ref, handle: null });
        if (out.reason === "cancelled") return removeAtt(key);
        patchAtt(key, { phase: "error", handle: null,
                        note: t(chatFiles.REASON_KEY[out.reason] || "chat.attachFailed",
                                { name, max: chatFiles.fmtSize(L.max_file_bytes) }) });
      });
    }
  };
  const attChip = (x) => h("div", { class: "cw-att-chip " + x.phase, "data-phase": x.phase },
    x.local ? h("img", { class: "cw-att-thumb", src: x.local, alt: x.name })
            : h("span", { class: "cw-att-glyph" }, x.phase === "error" ? "⚠" : (KIND_GLYPH[x.kind] || "📎")),
    h("div", { class: "cw-att-meta" },
      h("div", { class: "cw-att-name" }, x.name),
      h("div", { class: "cw-att-sub" },
        x.phase === "error" ? x.note
          : x.phase === "up" ? `${x.pct || 0}% · ${chatFiles.fmtSize(x.size)}`
          : x.phase === "reading" ? t("chat.attachReading")
          : chatFiles.fmtSize(x.size)),
      x.phase === "up" ? h("div", { class: "cw-att-bar" }, h("span", { style: `width:${x.pct || 0}%` })) : null),
    h("button", { class: "cw-att-x", "aria-label": () => t(x.phase === "up" || x.phase === "reading" ? "chat.attachCancel" : "chat.attachRemove"),
                  title: () => t(x.phase === "up" || x.phase === "reading" ? "chat.attachCancel" : "chat.attachRemove"),
                  onClick: () => removeAtt(x.key) }, raw(CLOSE_ICON)));
  // Paste and drop onto the composer are HIS attachments: `stopPropagation` keeps main.js's window-level
  // handlers (which file a pasted image or a dropped file into the desktop's inbox) from taking them.
  const onComposerPaste = (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    const files = [];
    for (const it of items) if (it.kind === "file") { const f = it.getAsFile(); if (f) files.push(f); }
    if (!files.length) return;
    e.preventDefault(); e.stopPropagation();
    addFiles(files);
  };
  const [dropping, setDropping] = createSignal(false);
  const onComposerDrag = (e) => { e.preventDefault(); e.stopPropagation(); setDropping(e.type !== "dragleave"); };
  const onComposerDrop = (e) => {
    const files = (e.dataTransfer && e.dataTransfer.files) || [];
    e.preventDefault(); e.stopPropagation(); setDropping(false);
    if (files.length) addFiles(files);
  };

  const send = () => {
    if (!inputEl || !canSend() || attBusy()) return;
    const ready = pend().filter((x) => x.phase === "ready" && x.ref).map((x) => ({
      id: x.ref.episode_id, name: x.ref.name, kind: x.ref.kind, size: x.ref.size, thumb: x.ref.thumb || null }));
    if (!inputEl.value.trim() && !ready.length) return;
    submitChat(inputEl.value, ready);
    pend().forEach(forget);
    setPend([]);
    inputEl.value = ""; inputEl.focus();
  };

  // PROCESOS — a component of its own, mounted through its one bridge (`services/procesos-bridge.js`).
  const tasksHost = h("div", { class: "cw-tasks" });
  const procesos = mountProcesos(tasksHost);

  let clustersCol = null;   // the «Clusters» column (V2-086), a component of its own: frontend/side/clusters/

  // ── CONNECTORS (V2-561/V2-526) and NETWORK (V2-866) — columns of their own (`frontend/side/conectores/`,
  // `frontend/side/red/`), wired by their bridges and re-read while they are the open tab. «Connect» hands off to the
  // CREDENTIAL surface (ConfigPanel's connectors tab): this list is for browsing and asking, never a form (V2-520).
  const isTab = (id) => () => store.chatOpen() && store.chatTab() === id;
  const openConnectorConfig = (id) => { store.setConfigInitialTab("conectores"); store.setConfigConnector(id || null); store.setConfigOpen(true); };
  const connHost = h("div", { class: "cw-conn" }), redHost = h("div", { class: "cw-red" });
  mountConectores(connHost, { visible: isTab("conectores"), manage: openConnectorConfig });
  red.mountRed(redHost, { visible: isTab("red") });

  // ── APPS tab (V2-761): the widget catalogue (`side/apps/` via `apps-bridge.js`); entering it re-reads it.
  const appsHost = h("div", { class: "cw-apps" }), appsTab = mountAppsTab(appsHost);
  createEffect(() => { if (store.chatTab() !== "apps") appsTab.hide(); else if (store.chatOpen()) appsTab.show(); });

  // The dock classes are set IMPERATIVELY by applyDock/applyFloat, and this binding rewrites the whole
  // className whenever the tab or the open flag changes — so it silently wiped `docked`/`dock-left` while the
  // `dockSide` variable stayed set. The wall then rendered as a floating panel at left:0 and still reserved a
  // full column: the operator's screenshot of 2026-09-07, a floating chat with the entire desk pushed right.
  // Reproduced headless: classes `chatwall tab-chat open`, geometry top:232 h:480, `--chatdock-l: 420px`.
  // Reproducing the dock state here is what makes the two writers agree instead of racing (V2-608).
  const dockClass = () => (dockSide ? " docked dock-" + dockSide : "");
  // `narrow` is a SIGNAL read by the class binding, never a classList write: the binding rebuilds the whole
  // className on any tab/open change and would wipe an imperative class — the exact V2-608 dock-class trap,
  // which this file has now paid for twice.
  const [narrow, setNarrow] = createSignal(false);
  const [tight, setTight] = createSignal(false);
  const wall = h("div", { id: "chatwall", ref: el => (wallEl = el), class: () => "chatwall tab-" + store.chatTab() + (store.chatOpen() ? " open" : "") + dockClass() + (narrow() ? " cw-narrow" : "") + (tight() ? " cw-tight" : "") },
    h("div", { class: "cw-head", ref: el => (headEl = el) },
      // V2-621 — the header reads «active tab NAME (fixed min-width) | five icon tabs | ⧉ ×» (operator,
      // 2026-09-08). The standing name says WHERE you are once the tabs are icons; CSS hides it when the
      // wall is wide enough for every tab to carry its own label beside its icon («si se amplían los
      // anchos se ve el icono y la desc al lado»).
      h("div", { class: "cw-tabname" }, () => t(TAB_LABEL[store.chatTab()] || "chat.tabChat")),
      // Each tab carries an ICON + a LABEL: wide, both show side by side; narrow (the wall's own
      // ResizeObserver toggles `cw-narrow`), the labels give way and the header's standing name takes
      // over — V2-619/V2-621. Never a clipped word.
      h("div", { class: "cw-tabs" },
        h("button", { class: () => "cw-tab" + (store.chatTab() === "chat" ? " on" : ""), title: () => t("chat.tabChat"), onClick: () => store.setChatTab("chat") }, raw(MESSAGE_SQUARE_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabChat"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "procesos" ? " on" : ""), title: () => t("chat.tabTasks"), onClick: () => store.setChatTab("procesos") }, raw(ACTIVITY_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabTasks"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "clusters" ? " on" : ""), title: () => t("chat.tabClusters"), onClick: () => store.setChatTab("clusters") }, raw(SERVER_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabClusters"))),
        () => (red.on() ? h("button", { class: () => "cw-tab" + (store.chatTab() === "red" ? " on" : ""), title: () => t("a2a.network"), onClick: () => store.setChatTab("red") }, raw(SERVER_ICON), h("span", { class: "cw-tab-label" }, () => t("a2a.network"))) : null),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "conectores" ? " on" : ""), title: () => t("chat.tabConnectors"), onClick: () => store.setChatTab("conectores") }, raw(LINK_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabConnectors"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "apps" ? " on" : ""), title: () => t("chat.tabApps"), onClick: () => store.setChatTab("apps") }, raw(WIDGETS_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabApps"))),
      ),
      // MODE TOGGLE — the box↔column switch, visible in BOTH shapes (operator, 2026-09-08: «en la box se
      // tienen que ver tb los 2 icons a la derecha, para pasar el formato box a columna»). Docked, it gives
      // the floating panel back («se minimiza la barra y vuelve a aparecer el widget del chat», 2026-09-07 —
      // still needed because the AGENT can open the wall docked); floating, it docks a full-height column on
      // the side it last occupied. The × beside it only ever CLOSES.
      h("button", { class: "cw-undock hb-icbtn", ref: el => (undockEl = el),
                    title: () => t(isDocked() ? "chat.undock" : "chat.dock"),
                    onClick: () => { if (dockSide) applyFloat(floatGeo || defaultFloat());
                                     else applyDock(lastDockSide, (loadDock() || {}).w || DOCK_DEF_W); } },
        () => (isDocked() ? "⧉" : "◫")),
      h("button", { class: "cw-x hb-icbtn", title: () => t("chat.close"), onClick: () => store.setChatOpen(false) }, raw(CLOSE_ICON)),
    ),
    // CHAT
    h("div", { class: "cw-list", ref: el => (listEl = el) }),
    // WIDGET confirmation (V2-518) — house rule: no popups; a pending question (delete /
    // restore / irreversible data operation) is shown IN the conversation with Yes/No, and answered here or by voice.
    // Mirror of the cluster gate below; same backend record (widgets/confirm.py), one at a time.
    () => (store.widgetConfirm()
      ? h("div", { class: "cl-confirm cw-wconfirm" },
          h("div", { class: "cl-q" }, store.widgetConfirm().question || t("chat.widgetConfirmQ")),
          h("div", { class: "cl-cbtns" },
            h("button", { class: "cl-b on", onClick: () => store.widgetConfirmResolve(true) }, () => t("chat.yes")),
            h("button", { class: "cl-b", onClick: () => store.widgetConfirmResolve(false) }, () => t("chat.no")),
          ))
      : null),
    AskWall(wallTraces),   // V2-851 — the open question of each waiting task, bound to its task and answerable here
    // PROCESOS (V2-728 · renamed V2-744) — one tab, four sub-tabs. The old «Procesos» and «Crons» were the same object seen
    // twice: a commission the brain is carrying out, and a commission with a clock on it.
    tasksHost,
    h("div", { class: "cw-clusters", ref: (el) => (clustersCol = mountClusters(el)) }),   // CLUSTERS (V2-086)
    redHost, connHost,   // NETWORK (off: no tab, no body) and CONECTORES — mounted above
    appsHost,   // APPS (V2-761) — the widget catalogue, its own component (`side/apps/`), drawn only while open
    // INPUT (Chat only — CSS hides it in the other tabs)
    h("div", { class: () => "cw-input" + (dropping() ? " cw-dropping" : ""),
               onDragover: onComposerDrag, onDragenter: onComposerDrag, onDragleave: onComposerDrag,
               onDrop: onComposerDrop },
      () => (pend().length ? h("div", { class: "cw-att-tray" }, ...pend().map(attChip)) : null),
      h("input", { type: "file", class: "cw-att-input", accept: ACCEPT, multiple: true, ref: (el) => (fileEl = el),
                   onChange: () => { addFiles(fileEl.files); fileEl.value = ""; } }),
      h("textarea", {
        onPaste: onComposerPaste,
        // rows:3 — the composer is for WRITING (V2-619, operator: «ya de base debería tener dos o tres
        // líneas de altura»); CSS gives it the matching min-height so a profile's type scale keeps the ratio.
        ref: el => (inputEl = el), rows: 3, placeholder: () => t("chat.messagePlaceholder"),
        onKeydown: e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } },
      }),
      // V2-831 T-03 — attach over send, ONE column right of the box: the text box keeps the whole width.
      h("div", { class: "cw-actions" }, h("button", { class: "cw-clip", title: () => t("chat.attach"),
          "aria-label": () => t("chat.attach"), onClick: () => fileEl && fileEl.click() }, raw(PAPERCLIP_ICON)),
        h("button", { class: () => "cw-send" + (canSend() && !attBusy() ? "" : " off"),
                      disabled: () => !canSend() || attBusy(),
                      title: () => t(!canSend() ? "chat.sendAgentOff" : attBusy() ? "chat.sendWaitFiles" : "chat.send"),
                      onClick: send }, raw(SEND_SVG))),
    ),
  );

  // When ENTERING a tab, refresh its data (live items already arrive via SSE; history/crons are requested here).
  createEffect(() => {
    const t = store.chatTab();
    if (!store.chatOpen()) return;
    if (t === "procesos") procesos.show();
    else if (t === "clusters") clustersCol.show();
  });
  // Leaving «Procesos» (another tab, or the wall closed) hides it: its refetch on a live change stops.
  createEffect(() => { if (!(store.chatOpen() && store.chatTab() === "procesos")) procesos.hide(); });

  // CHAT and VOICE are INDEPENDENT (V2-088). Opening this panel does NOT affect the speaker, and muting the speaker does not affect
  // this panel. The “chat mode = voice off” behavior from V2-054 is removed: it assumed opening chat meant “I want to
  // read instead of listen”, and that is FALSE — the panel has four tabs, and the operator may inspect PROCESSES,
  // CRONS, or CLUSTERS without wanting to silence anyone. Cutting off the voice merely by looking at a list is a decision the
  // system has no reason to make on its own, and it even cost an entire session that thought TTS was broken.
  //
  // Who mutes: ONLY the 🔊 icon (`session.toggleBotMute`). Chat is NOT a mode; it is an ADDITIONAL VIEW.
  createEffect(() => {
    store.chatOpen();      // sole dependency: reserved geometry depends on whether it is open
    setReserve();          // closing releases the reserved strip; reopening while docked re-applies it
  });

  // Remember open/closed + which tab, on every change — including the ones the ENGINE makes (a proactive push
  // opens the wall by SSE, `[[close]]` shuts it). Those are as much «where he left it» as a click is.
  createEffect(() => { store.chatOpen(); store.chatTab(); saveOpen(); });
  // The same (open, tab) reaches the timeline once per CHANGE, so a session replay knows the column at any step; the
  // mount's restore is a client state transition (`uiState`), the later ones his clicks or the engine's pushes.
  let _wallSaid = "";
  createEffect(() => { const o = !!store.chatOpen(), tab = store.chatTab(), k = o + ":" + tab; if (k === _wallSaid) return;
    const first = !_wallSaid; _wallSaid = k; (first ? api.uiState : api.uiEvent)("wall:state", { state: o ? "open" : "closed", detail: tab }); });

  // V2-619/V2-621 (V2-761: six now): below this width the tabs cannot all carry icon+label, so the labels give way to
  // the icons and the header's standing tab NAME takes over (CSS keys off `cw-narrow`). Measured on the wall
  // itself, so a dock resize, a float resize and a profile's larger type all take the same door. 660, not
  // V2-619's 580: wide tabs now keep their icons BESIDE the labels (~24px more per tab).
  const TABS_NARROW_BELOW = 660;
  // V2-761 — below this even the ICONS do not fit beside the standing tab name: measured with five tabs, the
  // strip needs 183px and a 320px wall (the default float) gave it 132, so the last two tabs sat behind a
  // hidden scrollbar — and with four, Conectores already did. Here the name gives way (the active tab is
  // still marked, and every icon keeps its title) rather than a tab becoming unreachable.
  const TABS_TIGHT_BELOW = 400;
  try {
    new ResizeObserver(() => {
      if (wallEl.offsetWidth > 0) {
        setNarrow(wallEl.offsetWidth < TABS_NARROW_BELOW);
        setTight(wallEl.offsetWidth < TABS_TIGHT_BELOW);
      }
    }).observe(wallEl);
  } catch (_) {}

  // ── geometry: floating ↔ dock ────────────────────────────────────────────────────────────────────────────
  function defaultFloat() { return { left: 18, top: 232, w: 320, h: Math.min(Math.round(innerHeight * 0.6), 520) }; }

  function applyFloat(geo) {
    floatGeo = geo || floatGeo || defaultFloat();
    dockSide = null; dockW = DOCK_DEF_W;
    wallEl.classList.remove("docked", "dock-left", "dock-right");
    wallEl.style.right = "auto"; wallEl.style.bottom = "auto";
    wallEl.style.left = _num(floatGeo.left, 18) + "px"; wallEl.style.top = _num(floatGeo.top, 232) + "px";
    wallEl.style.width = _num(floatGeo.w, 320) + "px"; wallEl.style.height = _num(floatGeo.h, 480) + "px";
    try { localStorage.setItem(FLOAT_KEY, JSON.stringify(floatGeo)); localStorage.removeItem(DOCK_KEY); } catch (_) {}
    setReserve();
  }

  function saveFloatFromEl() {
    const r = wallEl.getBoundingClientRect();
    floatGeo = { left: Math.round(r.left), top: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    dockSide = null;
    try { localStorage.setItem(FLOAT_KEY, JSON.stringify(floatGeo)); localStorage.removeItem(DOCK_KEY); } catch (_) {}
    setReserve();
  }

  function applyDock(side, w) {
    dockSide = side;
    placed = true;                              // a docked wall HAS a place: first-open auto-placement must not move it
    lastDockSide = side;                        // the ⧉ toggle re-docks a floating box to this side (V2-621)
    const width = Math.max(DOCK_MIN_W, _num(w, DOCK_DEF_W));
    dockW = width;
    wallEl.classList.add("docked");
    wallEl.classList.toggle("dock-left", side === "left");
    wallEl.classList.toggle("dock-right", side === "right");
    wallEl.style.height = ""; wallEl.style.top = ""; wallEl.style.bottom = "";
    wallEl.style.width = width + "px";
    if (side === "left") { wallEl.style.left = "0px"; wallEl.style.right = "auto"; }
    else { wallEl.style.left = "auto"; wallEl.style.right = "0px"; }
    try { localStorage.setItem(DOCK_KEY, JSON.stringify({ side, w: width })); } catch (_) {}
    setReserve();
  }

  // dock preview bar while dragging near an edge
  function showPreview(side) {
    if (!side) return hidePreview();
    if (!previewEl) { previewEl = document.createElement("div"); previewEl.className = "hb-dock-preview"; document.body.appendChild(previewEl); }
    const w = (loadDock() || {}).w || DOCK_DEF_W;
    previewEl.style.width = Math.max(DOCK_MIN_W, w) + "px";
    previewEl.classList.toggle("left", side === "left");
    previewEl.classList.toggle("right", side === "right");
    previewEl.style.display = "block";
  }
  function hidePreview() { if (previewEl) previewEl.style.display = "none"; }

  // SPACE RESERVATION: when chat is OPEN and docked, the desktop shifts into the free area.
  function setReserve() {
    const root = document.documentElement, body = document.body;
    body.classList.remove("chatdock-l", "chatdock-r");
    if (store.chatOpen() && dockSide) {
      // The INTENDED width, not the measured one. `offsetWidth` is 0 while the wall is still unlaid-out — which
      // is exactly the case on the restore path — so this used to reserve the 340px default for a 420px column
      // and leave an 80px band of desk hidden underneath it (measured 2026-09-07, V2-608). Measure only as a
      // fallback, for the resize drag, where the element is on screen and the pointer is the authority.
      const w = Math.round(dockW || wallEl.offsetWidth || DOCK_DEF_W);
      root.style.setProperty("--chatdock-l", dockSide === "left" ? w + "px" : "0px");
      root.style.setProperty("--chatdock-r", dockSide === "right" ? w + "px" : "0px");
      body.classList.add(dockSide === "left" ? "chatdock-l" : "chatdock-r");
    } else {
      root.style.setProperty("--chatdock-l", "0px");
      root.style.setProperty("--chatdock-r", "0px");
    }
    // The mode toggle's face is driven from HERE and nowhere else. Its first shape was a reactive `class`
    // binding on `dockSide` — a plain variable, not a signal, so it evaluated once at build time and the
    // button stayed hidden forever (measured: `undockVisible: false` with the wall fully docked). Every path
    // that changes `dockSide` already calls setReserve(), so mirroring it into the signal here is the one
    // place that cannot be forgotten (V2-621: the button now shows in BOTH shapes and only its face flips).
    setIsDocked(!!dockSide);
    // V2-608 — SAY SO. `#desk` follows these vars in CSS, but the widget cards live on `.hb-stage` (inset:0) in
    // viewport coordinates, so nothing moved them: the operator docked the chat left, the desk shrank underneath
    // his cards, and the one on the right was cut off by the window edge with no way to reach it. The desktop
    // listens and refits everything into the canvas that is left. Same shape as the rail's `hb:rail-resized`.
    try { document.dispatchEvent(new CustomEvent("hb:canvas-resized", { detail: { side: dockSide } })); } catch (_) {}
  }

  // ── MOVABLE by the header, with dock/undock ───────────────────────────────────────────────────────────────
  headEl.style.touchAction = "none";
  let drag = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0, pid = null, preview = null;
  headEl.addEventListener("pointerdown", e => {
    if (e.target.closest(".cw-x") || e.target.closest(".cw-tab") || e.target.closest(".cw-undock")) return;   // buttons do not drag
    drag = true; moved = false; pid = e.pointerId; sx = e.clientX; sy = e.clientY;
  });
  headEl.addEventListener("pointermove", e => {
    if (!drag) return;
    if (!moved) {
      if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) <= 4) return;
      moved = true; wallEl.classList.add("hb-dragging");
      try { headEl.setPointerCapture(pid); } catch (_) {}
      wallEl.style.right = "auto"; wallEl.style.bottom = "auto";
      if (dockSide) {
        const g = floatGeo || defaultFloat();
        wallEl.classList.remove("docked", "dock-left", "dock-right");
        wallEl.style.width = g.w + "px"; wallEl.style.height = g.h + "px";
        dockSide = null; setReserve();
        ox = Math.max(0, Math.min(e.clientX - g.w / 2, innerWidth - g.w));
        oy = Math.max(0, Math.min(e.clientY - 16, innerHeight - g.h));
        sx = e.clientX; sy = e.clientY;
      } else {
        const rr = wallEl.getBoundingClientRect();
        ox = rr.left; oy = rr.top;
      }
    }
    const x = Math.max(0, Math.min(ox + (e.clientX - sx), innerWidth - wallEl.offsetWidth));
    const y = Math.max(0, Math.min(oy + (e.clientY - sy), innerHeight - wallEl.offsetHeight));
    wallEl.style.left = x + "px"; wallEl.style.top = y + "px";
    preview = (e.clientX <= DOCK_PX) ? "left" : (e.clientX >= innerWidth - DOCK_PX) ? "right" : null;
    showPreview(preview);
  });
  const endDrag = () => {
    if (!drag) return; drag = false; wallEl.classList.remove("hb-dragging");
    if (!moved) return;
    hidePreview();
    if (preview) applyDock(preview, (loadDock() || {}).w || Math.round(wallEl.offsetWidth));
    else saveFloatFromEl();
    preview = null;
  };
  headEl.addEventListener("pointerup", endDrag);
  headEl.addEventListener("pointercancel", endDrag);

  // ── RESIZABLE from any edge/corner. Docked: only the inner edge is live (CSS) → it sets the column width. ──
  makeResizable(wallEl, {
    minW: MIN_W, minH: MIN_H,
    onChange: (rect) => {
      if (dockSide) {
        const width = Math.max(DOCK_MIN_W, Math.round(rect.width));
        dockW = width;
        wallEl.style.width = width + "px"; wallEl.style.top = ""; wallEl.style.bottom = ""; wallEl.style.height = "";
        if (dockSide === "left") { wallEl.style.left = "0px"; wallEl.style.right = "auto"; }
        else { wallEl.style.left = "auto"; wallEl.style.right = "0px"; }
        try { localStorage.setItem(DOCK_KEY, JSON.stringify({ side: dockSide, w: width })); } catch (_) {}
        setReserve();
      } else {
        saveFloatFromEl();
      }
    },
  });

  // ── restore geometry ────────────────────────────────────────────────────────────────────────────────────
  let placed = false;
  // V2-464 — SHOWCASE mode (?showcase=1): chat starts OPEN and DOCKED on the left, so an unattended
  // recording shows the conversation without anyone touching anything. Before the saved float: in the studio,
  // persisted geometry belongs to another session and a half-positioned floating chat covers the cards.
  const _showcase = new URLSearchParams(location.search).has("showcase");
  // V2-608 — THE SAVED DOCK IS RESTORED FIRST. It was written on every dock (DOCK_KEY, as this file's header
  // has said since V2-062) and then never read back except to seed the preview width, so `floatGeo` — which
  // `applyDock` does NOT clear — always won and the wall came back FLOATING. Measured on the real page: dock
  // left, reload, and it returns at left:18 w:320 with `hb_chat_dock` still holding {side:"left",w:420} and
  // `--chatdock-l` back to 0px. V2-550 fixed «it does not come back where it was» for the floating wall; this is
  // the same report for the docked one, and it is the shape the operator actually uses.
  const savedDock = loadDock();
  if (_showcase) {
    applyDock("left", (savedDock || {}).w || DOCK_DEF_W);
    placed = true;
    store.setChatOpen(true);
  } else if (savedDock) { applyDock(savedDock.side, savedDock.w); placed = true; }
  else if (floatGeo) { applyFloat(floatGeo); placed = true; }

  window.addEventListener("resize", () => { if (dockSide) applyDock(dockSide, wallEl.offsetWidth); });
  setReserve();

  // WHO OPENED IT decides the shape of a wall that has none yet (operator, 2026-10-04): «al inicializar un agente,
  // cuando abro la barra izquierda se abre anidada a la izquierda, no en ventana flotante. Solo en ventana
  // flotante desde el orbe central, siempre que no se haya abierto ya y pegado a la izquierda. En ese caso
  // respetamos el estado actual de UI y abrimos ahí». So: from the BAR, a floating (or never-placed) wall docks
  // to the left column; from the ORB, a docked wall stays docked and anything else floats, which is what the
  // saved float already does. The hint is consumed here so a later open by the agent or a push reads nothing.
  // `dockSide` is a plain variable read inside the effect on every run — not a one-shot binding (V2-608).
  createEffect(() => {
    if (!store.chatOpen()) return;
    const from = store.chatOpenFrom();
    if (!from) return;
    if (from === "bar" && !dockSide) applyDock("left", (loadDock() || {}).w || DOCK_DEF_W);
    store.setChatOpenFrom(null);
  });

  // THE CHAT WALL — a component of its own, mounted through its one bridge
  // (`services/wall-bridge.js`, INI-042 #49): every line is an action with an id, appended where it STARTS and never
  // rebuilt — his words, ours, a box. This file keeps the composer and hands the wall its look (`lineBody`,
  // `lineClasses`) and its boxes; the old path writes through `services/wall-legacy.js`, the manager through `wall`.
  const wallStore = createWallStorage();
  const bridge = createWallBridge({
    mount: listEl, device: api.DEVICE, input: false, cap: WALL_CAP, storage: wallStore,
    labels: { cut: "…", get earlier() { const at = wallStore.at(); return at ? t("chat.earlierAt", { when: ago(at / 1000) }) : t("chat.earlier"); } },
    renderers: { ref: (data) => chatRefView(data), a2a: (data) => a2a.a2aChatView(data), ask: (data) => askBox(data) },
    format: lineBody, classes: lineClasses,
    send: (text, id) => session.sendText(text, id),
  });
  // An open question whose turn is on the wall is a box of its own under it: appended when it opens, repainted in
  // place, gone when it closes (`legacy.asks`); one with no turn on the wall stays in the block at the foot.
  createEffect(() => legacy.asks(anchoredAsks(wallTraces())));

  // Opening the wall (or coming back to its Chat tab) lands on the latest message: a list filled while the wall was
  // hidden has no height to scroll, so the pin happens when the list becomes VISIBLE, after layout.
  function pinToLatest() { if (listEl) listEl.scrollTop = listEl.scrollHeight; }
  createEffect(() => {
    if (!store.chatOpen() || store.chatTab() !== "chat") return;
    requestAnimationFrame(pinToLatest);
  });

  // on first open with NO saved geometry: auto-place like a widget, then focus the input (Chat only)
  createEffect(() => {
    if (!store.chatOpen()) return;
    // Checked again INSIDE the frame: opening from the bar docks the wall in an effect that runs in the same
    // tick, and placeWall writes an inline `left` the docked CSS does not override — the column stayed full
    // height but shifted right, over the desk, until a reload restored it from DOCK_KEY.
    if (!placed) requestAnimationFrame(() => { if (!placed && !dockSide) placeWall(wallEl); placed = true; });
    if (inputEl && store.chatTab() === "chat") inputEl.focus();
  });

  return wall;
}

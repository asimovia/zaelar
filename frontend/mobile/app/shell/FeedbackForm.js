// ============================================================================
// FeedbackForm.js — the phone's feedback, at PARITY with the desktop panel (operator, 2026-10-24: «totalmente
// funcional igual que en desktop»). Rendered inline in MenuSheet, opened by its row or by the dock's button.
//
// Everything that decides something is SHARED with app/components/FeedbackWidget.js, never re-derived here:
//   · send / list / quick marks → services/feedback-api.js
//   · what a send or a list answered → services/feedback-state.js (sendOutcome / listOutcome / lineFor)
//   · dictation → services/feedback-dictation.js · pictures → services/feedback-images.js (budget, refusals)
// Only the LAYOUT is this shell's: two tabs (New · Sent), the kind, email, text, pictures, then one footer row —
// the two quick hands at the left, mic · clip · send at the right, as on the desktop.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import { createSignal, createEffect } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { CLOSE_ICON, MIC_ICON, PAPERCLIP_ICON, SEND_ICON, THUMBS_DOWN_ICON, THUMBS_UP_ICON } from "../../../app/lib/icons.js?v=2";
import * as feedbackApi from "../../../app/services/feedback-api.js?v=1";
import { sendOutcome, listOutcome, lineFor } from "../../../app/services/feedback-state.js?v=1";
import * as dictation from "../../../app/services/feedback-dictation.js?v=1";
import * as shotsvc from "../../../app/services/feedback-images.js?v=1";

const fmtDate = (iso) => {
  try { return iso ? new Date(iso).toLocaleString(store.lang() || undefined, { dateStyle: "medium", timeStyle: "short" }) : ""; }
  catch (_) { return iso || ""; }
};
const excerpt = (s, max = 180) => { s = (s || "").trim(); return s.length > max ? s.slice(0, max).trimEnd() + "…" : s; };

/** `open` is a signal: the form refreshes its Sent list while it is open (every 30 s, like the desktop panel). */
export function FeedbackForm(open) {
  let textEl = null, emailEl = null, fileEl = null, recHandle = null, base = "", finalSoFar = "", pollTimer = null;
  const [tab, setTab] = createSignal("new");
  const [kind, setKind] = createSignal("issue");
  const [line, setLine] = createSignal("");
  const [thanks, setThanks] = createSignal(false);
  const [listening, setListening] = createSignal(false);
  const [shots, setShots] = createSignal([]);
  const [shotLine, setShotLine] = createSignal("");
  const [quick, setQuick] = createSignal("");          // "" | "sending" | "done" | "failed"
  const [quickDir, setQuickDir] = createSignal("");
  const [reachable, setReachable] = createSignal(true);
  const [emptyKey, setEmptyKey] = createSignal("feedback.emptyState");

  const refresh = async () => {
    const out = listOutcome(await feedbackApi.listFeedback());
    setReachable(out.reachable); setEmptyKey(out.emptyKey); store.setFeedbackItems(out.items);
  };
  createEffect(() => {
    if (open()) { refresh(); clearInterval(pollTimer); pollTimer = setInterval(refresh, 30000); }
    else { clearInterval(pollTimer); pollTimer = null; if (listening()) toggleMic(); }
  });

  const render = (interim) => { if (textEl) textEl.value = [base, finalSoFar, interim].filter(Boolean).join(" "); };
  const toggleMic = () => {
    if (listening()) { dictation.stop(recHandle); recHandle = null; setListening(false); return; }
    if (!dictation.isSupported()) return;
    base = textEl ? textEl.value.trim() : ""; finalSoFar = "";
    recHandle = dictation.start({
      lang: store.lang(), onInterim: render,
      onFinal: (chunk) => { finalSoFar = [finalSoFar, chunk].filter(Boolean).join(" "); render(""); },
      onEnd: () => setListening(false),
    });
    setListening(true);
  };

  const addFiles = async (files) => {
    setShotLine("");
    for (const f of Array.from(files || [])) {
      if (!shotsvc.isImage(f)) { setShotLine(t("feedback.imagesOnly")); continue; }
      const shot = await shotsvc.prepare(f);
      if (!shot) { setShotLine(t("feedback.shotUnreadable")); continue; }
      const why = shotsvc.refusal(shots(), shot.bytes);
      if (why) { setShotLine(t(why)); continue; }
      setShots([...shots(), shot]);
    }
  };
  // A pasted screenshot belongs to THIS report: stop it before the window-level paste handler files it elsewhere.
  const onPaste = (e) => {
    const files = [];
    for (const it of (e.clipboardData && e.clipboardData.items) || []) {
      if (it.kind === "file" && /^image\//i.test(it.type)) { const f = it.getAsFile(); if (f) files.push(f); }
    }
    if (!files.length) return;
    e.preventDefault(); e.stopPropagation();
    addFiles(files);
  };

  const send = async () => {
    const message = (textEl && textEl.value || "").trim();
    if (!message || store.feedbackSending()) return;
    if (listening()) toggleMic();
    store.setFeedbackSending(true);
    const res = await feedbackApi.sendFeedback({ message, email: (emailEl && emailEl.value) || "",
      includeSessionEvidence: true, kind: kind(), shots: shots() });
    store.setFeedbackSending(false);
    const out = sendOutcome(res);
    if (!out.ok) { setLine(lineFor(out, t)); return; }     // the text stays, so a retry costs nothing
    setLine(""); textEl.value = ""; if (emailEl) emailEl.value = "";
    setShots([]); setShotLine("");
    setThanks(true); setTimeout(() => setThanks(false), 4000);
    setTab("sent");
    refresh();
  };

  const sendQuick = async (dir) => {
    if (quick()) return;
    setQuickDir(dir); setQuick("sending");
    const res = await feedbackApi.sendThumbs(dir);
    setQuick(res && res.ok ? "done" : "failed");
  };
  const quickDone = () => quick() === "done" || quick() === "failed";

  const item = (it) => h("div", { class: "zm-fbi" },
    h("div", { class: "zm-fbi-msg" }, excerpt(it.message)),
    h("div", { class: "zm-fbi-meta" }, fmtDate(it.created_at), " · ",
      h("span", { class: "zm-fbi-badge s-" + it.status }, () => t("feedback.status." + it.status))),
    it.reply_text ? h("div", { class: "zm-fbi-reply" }, h("b", null, () => t("feedback.replyLabel")), it.reply_text) : null,
  );

  return h("div", { class: () => "zm-fb" + (open() ? " open" : "") + " tab-" + tab() + (quickDone() ? " quick" : ""), onPaste },
    h("div", { class: "zm-fb-tabs" },
      h("button", { class: () => "zm-fb-tab" + (tab() === "new" ? " on" : ""), onClick: () => setTab("new") }, () => t("feedback.tabNew")),
      h("button", { class: () => "zm-fb-tab" + (tab() === "sent" ? " on" : ""), onClick: () => { setTab("sent"); refresh(); } }, () => t("feedback.tabSent")),
    ),
    () => (quickDone()
      ? h("div", { class: "zm-fb-quick", role: "status" },
          h("div", { class: "zm-fb-quick-mark " + (quickDir() === "up" ? "up" : "down"), html: quickDir() === "up" ? THUMBS_UP_ICON : THUMBS_DOWN_ICON }),
          h("p", null, quick() === "failed" ? t("feedback.quickFailed") : t(quickDir() === "up" ? "feedback.thumbsUpThanks" : "feedback.thumbsDownThanks")),
          h("button", { class: "zm-primary", onClick: () => { setQuick(""); setQuickDir(""); } },
            quick() === "failed" ? t("feedback.back") : t("feedback.close")))
      : null),
    () => (thanks() ? h("p", { class: "zm-fb-done" }, t("feedback.thanks")) : null),
    () => (line() ? h("p", { class: "zm-fb-err" }, line()) : null),
    h("div", { class: "zm-fb-new" },
      h("div", { class: "zm-fb-kind" },
        h("button", { class: () => "zm-fb-kind-b" + (kind() === "issue" ? " on" : ""), onClick: () => setKind("issue") }, () => t("feedback.kindIssue")),
        h("button", { class: () => "zm-fb-kind-b" + (kind() === "idea" ? " on" : ""), onClick: () => setKind("idea") }, () => t("feedback.kindIdea")),
      ),
      h("input", { type: "email", class: "zm-fb-email", placeholder: () => t("feedback.emailPlaceholder"), ref: (el) => (emailEl = el) }),
      h("textarea", { rows: "4", ref: (el) => (textEl = el),
        placeholder: () => t(kind() === "idea" ? "feedback.placeholderIdea" : "feedback.placeholderIssue") }),
      () => (shots().length
        ? h("div", { class: "zm-fb-shots" }, ...shots().map((sh, i) => h("div", { class: "zm-fb-shot" },
            h("img", { src: shotsvc.dataUrl(sh), alt: () => t("feedback.shotAlt") }),
            h("button", { "aria-label": () => t("feedback.shotRemove"), onClick: () => setShots(shots().filter((_, n) => n !== i)) }, raw(CLOSE_ICON)))))
        : null),
      () => (shotLine() ? h("small", { class: "zm-fb-shotnote" }, shotLine()) : null),
      h("small", null, () => t("mobile.feedback_evidence")),
      h("input", { type: "file", class: "zm-fb-file", accept: "image/*", multiple: true, ref: (el) => (fileEl = el),
        onChange: () => { addFiles(fileEl.files); fileEl.value = ""; } }),
      h("div", { class: "zm-fb-row" },
        h("button", { class: "zm-fb-ic up", "aria-label": () => t("feedback.thumbsUpLabel"), onClick: () => sendQuick("up") }, raw(THUMBS_UP_ICON)),
        h("button", { class: "zm-fb-ic down", "aria-label": () => t("feedback.thumbsDownLabel"), onClick: () => sendQuick("down") }, raw(THUMBS_DOWN_ICON)),
        h("span", { class: "zm-fb-gap" }),
        h("button", { class: () => "zm-fb-ic" + (listening() ? " on" : "") + (dictation.isSupported() ? "" : " hidden"),
          "aria-label": () => (listening() ? t("feedback.dictating") : t("feedback.dictate")), onClick: toggleMic }, raw(MIC_ICON)),
        h("button", { class: "zm-fb-ic", "aria-label": () => t("feedback.attach"), onClick: () => fileEl && fileEl.click() }, raw(PAPERCLIP_ICON)),
        h("button", { class: "zm-primary zm-fb-send", disabled: () => store.feedbackSending(), onClick: send },
          raw(SEND_ICON), h("span", null, () => (store.feedbackSending() ? t("feedback.sending") : t("feedback.send")))),
      ),
    ),
    h("div", { class: "zm-fb-sent" },
      () => (store.feedbackItems().length
        ? store.feedbackItems().map(item)
        : h("p", { class: "zm-fb-empty" + (reachable() ? "" : " unreachable") }, () => t(emptyKey()))),
    ),
  );
}

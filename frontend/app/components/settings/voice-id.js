// Settings › Voice › Voice recognition — «Stick to my voice» and the voice it sticks to (V2-651 F1).
//
// The switch here is a MIRROR of the orb bar's: the SAME setting (services/voice-lock.js, kept on this device), so a
// click on the bar moves this box and Save here moves the bar. Under the bar, acting on its own (`data-set-live`): what
// is known about the kept voice, and «Train my voice» — the only place to re-learn it — which sets the kept voice aside,
// asks him to speak for a few seconds and keeps the new voice only when the enrolment completes.
import { t } from "../../core/i18n.js?v=1";
import { createEffect } from "../../core/reactive.js?v=2";
import { esc, row, group, page, btn, bindForm, say } from "./layout.js?v=1";
import { voiceLock, voiceEnrolled, voiceLearnedAt, voiceTraining, setVoiceLock, train } from "../../services/voice-lock.js?v=1";

const stateText = () => {
  const tr = voiceTraining();
  if (tr) return t("config.voiceid.state_training", { count: tr.count, need: tr.need || "…" });
  if (!voiceEnrolled()) return t("config.voiceid.state_none");
  const at = voiceLearnedAt();
  return at ? t("config.voiceid.state_learned", { when: new Date(at).toLocaleString() }) : t("config.voiceid.state_learned_old");
};

export function sec_voiceid() {
  return page({ id: "voiceid", crumb: [t("config.sec.voice"), t("config.sec.voiceid")], title: t("config.voiceid.title"),
    sub: t("config.voiceid.sub"), form: true,
    body: group(row(t("config.voiceid.lock"),
      `<input type="checkbox" id="cf_vid_lock"${voiceLock() ? " checked" : ""}/>`, esc(t("config.voiceid.lock_hint")), "cf_vid_lock")),
    after: group(
      row(t("config.voiceid.state"), `<span id="cf_vid_state">${esc(stateText())}</span>`) +
      row(t("config.voiceid.train"), btn(t("config.voiceid.train_btn"), { cls: "cf-vid-train" }), esc(t("config.voiceid.train_hint"))),
      { title: t("config.voiceid.voice_title"), attrs: 'id="cf_vid_voice" data-set-live' }) });
}

/** Wires the page: Save writes the shared switch; the bar's clicks reach the box while it is not being edited. */
export function wireVoiceId(pg, { reset } = {}) {
  if (!pg) return () => {};
  const box = pg.querySelector("#cf_vid_lock");
  const form = bindForm(pg, { save: async () => { setVoiceLock(box.checked, "settings"); return { ok: true }; }, reset });
  const stops = [];
  stops.push(createEffect(() => {
    const on = voiceLock();
    if (!pg.isConnected) return;
    if (!pg.classList.contains("is-dirty") && box.checked !== on) { box.checked = on; if (form) form.snap(); }
  }));
  const st = pg.querySelector("#cf_vid_state");
  const trainB = pg.querySelector(".cf-vid-train");
  stops.push(createEffect(() => {
    const txt = stateText(), busy = !!voiceTraining();
    if (st) st.textContent = txt;
    if (trainB) trainB.disabled = busy;
  }));
  if (trainB) trainB.onclick = async () => {
    say(pg, t("config.voiceid.train_go"), "busy");
    const r = await train();
    say(pg, r.ok ? "✓ " + t("config.voiceid.train_ok") : "✗ " + t("config.voiceid.train_fail_" + (r.why === "no_session" || r.why === "timeout" ? r.why : "other")),
      r.ok ? "ok" : "error");
  };
  // The effects end with the page: the panel redraws by replacing its HTML.
  const gone = new MutationObserver(() => { if (!pg.isConnected) { stops.forEach((s) => s()); gone.disconnect(); } });
  if (pg.parentNode) gone.observe(document.body, { childList: true, subtree: true });
  return () => { stops.forEach((s) => s()); gone.disconnect(); };
}

// self-controls.js — his own 🔊 / ⏻ ordered by VOICE (nucleo/acts/self_controls.py): this screen presses its button.
//
// The brain emits one `controls` event, scoped to the screen that heard him (`event-scope.js`: `controls` is
// origin-scoped), and this module runs THE BUTTON'S DOOR, never a copy of it: the 🔊 does what the bar's speaker does
// (bring the speaker here when it is muted, else the toggle — Orb.js / DockBar.js) and «off» runs `power.setPower`, the
// ⏻'s own body (server first, then the session). Both are imported lazily: session.js imports sse.js, which imports
// this, so a static import would close the cycle.
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

/** Apply one `controls` act (`mute` · `unmute` · `off`). Idempotent: a state already reached is left alone. */
export function applyControl(d) {
  const act = String((d && (d.act || d.label)) || "");
  if (act === "off") {
    import("./power.js?v=1").then(p => { if (!store.powerOff()) p.setPower(true, "voice"); }).catch(() => {});
  } else if (act === "voice_male" || act === "voice_female") {
    pickVoice(act === "voice_male" ? "m" : "f");
  } else if (act === "voice_list") {
    listVoices();
  } else if (act === "voice_settings") {
    store.setConfigInitialTab("settings"); store.setConfigInitialSection("voice"); store.setConfigOpen(true);
  } else if (act === "language") {
    flash("🌐 " + t("controls.language_locked"));      // the system language is fixed once initialised:
  } else if (act === "mute" || act === "unmute") {
    import("./session.js?v=3").then(session => {
      const muted = store.botMuted();
      if (act === "mute" && !muted) session.toggleBotMute();
      else if (act === "unmute" && muted) {
        if (session.openSpeakerHere) session.openSpeakerHere("voice"); else session.toggleBotMute();
      }
    }).catch(() => {});
  }
}

const flash = (text) => {
  store.setVoiceFlash({ text, show: true });
  clearTimeout(flash._t); flash._t = setTimeout(() => store.setVoiceFlash(f => ({ ...f, show: false })), 4000);
};

/** «try another male / female voice»: a random OTHER voice of that gender from the catalog, saved exactly as the
 *  ⚙ dropdown saves it (`assistant_voice` through `POST /api/settings`), so it persists and the next thing it says
 *  uses it (a live session reconnects, as `ConfigPanel.saveVoice` does). */
export async function pickVoice(gender, rnd = Math.random) {
  const api = await import("./api.js?v=2");
  const d = await api.voices();
  const ids = d.ids || [], labels = d.voices || [], genders = d.genders || [];
  const pool = ids.map((_, i) => i).filter(i => genders[i] === gender && i !== d.current);
  const pick = pool.length ? pool[Math.floor(rnd() * pool.length)] : -1;
  if (pick < 0) { flash("🗣 " + (labels[d.current] || "")); return null; }
  const r = await api.saveSettings({ assistant_voice: ids[pick] });
  if (r && r.ok) {
    flash("🗣 " + labels[pick]);
    const session = await import("./session.js?v=3");
    if (r.needs_reconnect) { try { await session.loadVoices(); } catch (_) {} if (session.isActive()) await session.reconnect(); }
  }
  return ids[pick];
}

/** «what voices do you have?»: the catalog, shown, with the settings opened on the dropdown that holds it. */
export async function listVoices() {
  const api = await import("./api.js?v=2");
  const d = await api.voices();
  flash("🗣 " + t("controls.voices") + ": " + (d.voices || []).join(" · "));
  store.setConfigInitialTab("settings"); store.setConfigInitialSection("voice"); store.setConfigOpen(true);
}

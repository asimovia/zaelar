// self-controls.js — his own 🔊 / volume / mic / ⏻ ordered by VOICE (nucleo/acts/self_controls.py): this screen presses its button.
//
// The brain emits one `controls` event, scoped to the screen that heard him (`event-scope.js`: `controls` is
// origin-scoped), and this module runs THE BUTTON'S DOOR, never a copy of it: the 🔊 does what the bar's speaker does
// (bring the speaker here when it is muted, else the toggle — Orb.js / DockBar.js), the volume is the slider's door
// (`volume.js`), the mic is the 🎤's (`mic.setMuted`) and «off» runs `power.setPower`, the ⏻'s own body. The doors are
// imported lazily (`doors`): session.js imports sse.js, which imports this, so a static import would close the cycle.
//
// THREE RULES that make it reliable (V2-930): every act names a TARGET STATE, so it reads the button first and a state
// already reached is left alone (never a blind toggle); the acts run ONE AFTER ANOTHER in the order he gave them
// («cállate y apágate»); and what the screen shows afterwards is read back from the button's state, not assumed.
// A ONE-WAY act (mic closed, agent off) first lets him hear its line — which names the button as the way back — then
// acts. Nothing here waits on a frame or on visibility: a locked phone's order runs the same path.
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as volume from "./volume.js?v=1";

/** The buttons' doors, lazily (a test may swap them). */
export const doors = {
  session: () => import("./session.js?v=3"),
  power: () => import("./power.js?v=1"),
  mic: () => import("./mic.js?v=1"),
  api: () => import("./api.js?v=2"),
};
let _queue = Promise.resolve();

/** Apply one `controls` act. Queued: each runs after the previous one finished, in the order they arrived. */
export function applyControl(d) {
  _queue = _queue.then(() => run(d)).catch(() => {});
  return _queue;
}

/** Bring the speaker here when it is muted — the 🔊's own door (Orb.js / DockBar.js). */
async function speakerOn(session) {
  if (!store.botMuted()) return;
  if (session.openSpeakerHere) await session.openSpeakerHere("voice"); else session.toggleBotMute();
}

async function run(d) {
  const act = String((d && (d.act || d.label)) || "");
  if (act === "off" || act === "mic_off") {
    await afterTheLine();
    if (act === "off") { const p = await doors.power(); if (!store.powerOff()) p.setPower(true, "voice"); }
    else { (await doors.mic()).setMuted(true, "voice"); flash(t("controls.mic_off_back")); }
  } else if (act === "mute" || act === "unmute") {
    const session = await doors.session();
    if (act === "mute") { if (!store.botMuted()) session.toggleBotMute(); }
    else await speakerOn(session);
    flash(t(store.botMuted() ? "voice.flash_muted" : "voice.flash_voice_on"));   // read back from the button
  } else if (act === "volume_up" || act === "volume_down" || act === "volume_set") {
    if (act === "volume_set") volume.setLevel(d.value); else volume.step(act === "volume_up" ? 1 : -1);
    // «louder» over a muted speaker means he wants to hear it: the 🔊 comes back too («quieter» leaves it muted).
    if (act !== "volume_down" && volume.level() > 0) await speakerOn(await doors.session());
    flash(volume.settable() ? t("controls.volume_at", { n: volume.level() }) : t("controls.volume_fixed"));
  } else if (act === "voice_male" || act === "voice_female") {
    pickVoice(act === "voice_male" ? "m" : "f");
  } else if (act === "voice_list") {
    listVoices();
  } else if (act === "voice_settings") {
    store.setConfigInitialTab("settings"); store.setConfigInitialSection("voice"); store.setConfigOpen(true);
  } else if (act === "presence_on" || act === "presence_off") {   // V2-928: its face, the ☺ button's own door
    import("../presence/state.js?v=1").then(p => p.setPresenceOn(act === "presence_on", "voice")).catch(() => {});
  } else if (act === "presence_settings") {   // the phone's own page when it has one, else Settings ▸ Presence
    import("../presence/state.js?v=1").then(p => { if (!p.openPresencePage()) { store.setConfigInitialTab("presence"); store.setConfigOpen(true); } }).catch(() => {});
  } else if (act === "language") {
    flash("🌐 " + t("controls.language_locked"));      // the system language is fixed once initialised
  } else return;
  // The audit reads the RESULT off the buttons, not the order.
  (await doors.api()).uiEvent("voice:controls", { act, speaker: store.botMuted() ? "muted" : "on", volume: volume.level(),
                                                  mic: store.micMuted() ? "muted" : "open", power: store.powerOff() ? "off" : "on" });
}

/** A one-way act waits for its line to be HEARD: the agent's speech on this screen starting and then staying quiet for
 *  a breath (the model's words and the act's line can be two utterances back to back), bounded; nothing to wait for
 *  when its voice is not heard here (speaker muted, no session). Timers, never frames. */
export const LINE_START_MS = 3500, LINE_QUIET_MS = 800, LINE_MAX_MS = 15000;
export function afterTheLine(tick = 100) {
  if (store.botMuted() || !store.started()) return Promise.resolve("unheard");
  const t0 = Date.now();
  let heard = false, quiet = 0;
  return new Promise((done) => {
    const poll = () => {
      const now = Date.now() - t0;
      if (store.botSpeaking()) { heard = true; quiet = 0; }
      else if (heard && !quiet) quiet = now;
      if (heard && quiet && now - quiet >= LINE_QUIET_MS) return done("said");
      if ((!heard && now >= LINE_START_MS) || now >= LINE_MAX_MS) return done("timeout");
      setTimeout(poll, tick);
    };
    poll();
  });
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

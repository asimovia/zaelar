// ============================================================================
// test_his_controls_move_the_buttons.mjs — V2-930, node 4.571.
//
// His own controls by VOICE land on the screen that heard him as one `controls` event, and this screen runs the
// button's door (services/self-controls.js). Driven here over the REAL `self-controls.js`, `volume.js`, `store.js`
// and `i18n.js`, with the four doors it presses (session · power · mic · api) swapped for recorders that move the
// same store signals the real buttons move. Pinned:
//   • mute / unmute name a TARGET STATE: said twice, the second press never happens (no blind toggle);
//   • what the screen shows afterwards is read BACK from the button — a door that failed to unmute says «muted»;
//   • the volume is 0–100, clamped, kept on this device (`hb_bot_volume`), and the bot's <audio> follows it (0 while
//     muted); «louder» over a muted speaker brings the speaker back, «quieter» leaves it muted;
//   • a one-way act (mic off, ⏻ off) waits for its line to be heard, then acts; with the voice not heard here it acts
//     at once;
//   • acts run in the order he gave them («mute, then off»).
//
// Run: node tests/browser/unit/voice/test_his_controls_move_the_buttons.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => ({ volume: 1 }) };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const { t } = await import("../../../../frontend/app/core/i18n.js?v=1");
const volume = await import("../../../../frontend/app/services/volume.js?v=1");
const sc = await import("../../../../frontend/app/services/self-controls.js?v=1");

const calls = [], audits = [];
let speakerDoorWorks = true;
const session = {
  toggleBotMute() { calls.push("toggle"); store.setBotMuted(!store.botMuted()); },
  async openSpeakerHere(why) { calls.push("open:" + why); if (speakerDoorWorks && store.botMuted()) store.setBotMuted(false); },
};
sc.doors.session = async () => session;
sc.doors.power = async () => ({ setPower(off, by) { calls.push(`power:${off}:${by}`); store.setPowerOff(off); } });
sc.doors.mic = async () => ({ setMuted(v, why) { calls.push(`mic:${v}:${why}`); store.setMicMuted(v); } });
sc.doors.api = async () => ({ uiEvent(a, o) { audits.push({ a, ...o }); } });
const reset = () => { calls.length = 0; audits.length = 0; };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const flash = () => store.voiceFlash().text;

store.setStarted(false); store.setBotMuted(false); store.setMicMuted(false); store.setPowerOff(false);

// ══ 1 · MUTE / UNMUTE are a target state, never a toggle ═══════════════════════════════════════════════════
reset();
await sc.applyControl({ act: "mute" });
await sc.applyControl({ act: "mute" });
assert.deepEqual(calls, ["toggle"], "«mute» twice must press the 🔊 once");
assert.equal(store.botMuted(), true);
assert.equal(flash(), t("voice.flash_muted"), "the screen says the state the button is in");
assert.equal(audits.at(-1).speaker, "muted", "the audit reads the result off the button");
reset();
await sc.applyControl({ act: "unmute" });
await sc.applyControl({ act: "unmute" });
assert.deepEqual(calls, ["open:voice"], "«unmute» twice must bring the speaker here once, through its own door");
assert.equal(store.botMuted(), false);
assert.equal(flash(), t("voice.flash_voice_on"));
// read back, never assumed: a door that could not bring the speaker here leaves the screen saying «muted»
store.setBotMuted(true); speakerDoorWorks = false; reset();
await sc.applyControl({ act: "unmute" });
assert.equal(flash(), t("voice.flash_muted"), "a failed unmute must not be shown as «voice on»");
assert.equal(audits.at(-1).speaker, "muted");
speakerDoorWorks = true; store.setBotMuted(false);

// ══ 2 · VOLUME: clamped, kept on this device, the element follows it ═══════════════════════════════════════
const el = { muted: false, volume: 1 };
volume.bind(el);
await sc.applyControl({ act: "volume_set", value: 30 });
assert.equal(volume.level(), 30);
assert.equal(mem.get("hb_bot_volume"), "30", "the level persists on this device");
assert.ok(Math.abs(el.volume - 0.3) < 1e-9, `the bot's audio plays at the level: ${el.volume}`);
assert.equal(flash(), t("controls.volume_at", { n: 30 }), "the screen shows the level the slider holds");
await sc.applyControl({ act: "volume_set", value: 150 });
assert.equal(volume.level(), 100, "a level over 100 is 100");
await sc.applyControl({ act: "volume_set", value: -5 });
assert.equal(volume.level(), 0, "a level under 0 is 0");
await sc.applyControl({ act: "volume_set", value: "loud" });
assert.equal(volume.level(), 0, "a level that is no number changes nothing");
await sc.applyControl({ act: "volume_up" });
assert.equal(volume.level(), volume.STEP);
await sc.applyControl({ act: "volume_down" }); await sc.applyControl({ act: "volume_down" });
assert.equal(volume.level(), 0, "quieter stops at 0");
await sc.applyControl({ act: "volume_set", value: 60 });
// muted: the element plays at 0 whatever the level; «quieter» leaves it muted; «louder» brings the speaker back
store.setBotMuted(true);
assert.equal(el.muted, true); assert.equal(el.volume, 0, "a muted speaker plays at 0");
reset();
await sc.applyControl({ act: "volume_down" });
assert.equal(store.botMuted(), true, "«quieter» must not un-mute");
assert.deepEqual(calls, []);
await sc.applyControl({ act: "volume_up" });
assert.equal(store.botMuted(), false, "«louder» over a muted speaker brings it back");
assert.deepEqual(calls, ["open:voice"]);
assert.ok(Math.abs(el.volume - 0.6) < 1e-9, `un-muted, it plays at his level again: ${el.volume}`);
// a fresh page on this device reads the level it was left at
const again = await import("../../../../frontend/app/services/volume.js?v=reload");
assert.equal(again.level(), 60, "the level survives a reload of this screen");

// ══ 3 · ONE WAY: the line first, then the act ══════════════════════════════════════════════════════════════
// voice not heard here (no session): acts at once
reset();
await sc.applyControl({ act: "mic_off" });
assert.deepEqual(calls, ["mic:true:voice"]);
assert.equal(store.micMuted(), true);
assert.equal(flash(), t("controls.mic_off_back"), "the screen names the button as the way back");
store.setMicMuted(false);
// voice heard here: waits for the line to start and to end, then switches off
store.setStarted(true); store.setBotMuted(false); reset();
const done = sc.applyControl({ act: "off" });
await sleep(150);
assert.deepEqual(calls, [], "it must not switch off before its line is heard");
store.setBotSpeaking(true);
await sleep(300);
assert.deepEqual(calls, [], "…nor while the line is being said");
store.setBotSpeaking(false);
await sleep(200);
store.setBotSpeaking(true);                       // a second utterance back to back (the act's own line)
await sleep(200);
assert.deepEqual(calls, [], "a short gap between two utterances is not the end of the line");
store.setBotSpeaking(false);
await done;
assert.deepEqual(calls, ["power:true:voice"]);
assert.equal(store.powerOff(), true);
// already off: nothing pressed again
reset(); store.setStarted(false);
await sc.applyControl({ act: "off" });
assert.deepEqual(calls, [], "an agent already off is left alone");
store.setPowerOff(false);

// ══ 4 · IN HIS ORDER: «mute, then switch off» ══════════════════════════════════════════════════════════════
store.setStarted(true); store.setBotMuted(false); reset();
sc.applyControl({ act: "mute" });
await sc.applyControl({ act: "off" });           // muted → the off line is not heard here → acts at once
assert.deepEqual(calls, ["toggle", "power:true:voice"]);

console.log("ok — his controls move the buttons");

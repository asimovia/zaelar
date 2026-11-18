// ============================================================================
// test_the_mic_icon_mirrors_the_wire.mjs — 2026-11-18, session af04be1f.
//
// The engine restarted, the screen reconnected, and the engine transcribed a sentence he was dictating elsewhere while
// he believed the 🎤 was off. Driven here over the REAL `services/mic.js`, `services/mic-wire.js` and `core/store.js`,
// with the LiveKit track and room replaced by recorders:
//   1. a reconnect with `hb_mic_muted=1` publishes the capture ALREADY disabled and muted — nothing is ever published
//      open, and the transport never asks for an enabled microphone;
//   2. the icon is the WIRE: a probe that says «sending» under a closed switch draws OPEN (the mismatch shows), and the
//      next heartbeat closes it (off wins) and says so;
//   3. the wire's own probe reads the publication (muted, ended or disabled = nothing leaves the page);
//   4. a fault with nothing sending is slashed; a fault over a sending mic is drawn open;
//   5. a new transport forgets what the engine was told (an engine restarted under the tab has a boot default, not
//      his switch), so the first apply re-sends it.
//
// Run: node tests/browser/unit/mic/test_the_mic_icon_mirrors_the_wire.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"], ["hb_mic_muted", "1"]]);   // he closed the mic before the restart
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
const posts = [];
globalThis.fetch = async (url, opts) => { posts.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
                                          return { ok: true, json: async () => ({ ok: true }), text: async () => "" }; };
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){} };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const mic = await import("../../../../frontend/app/services/mic.js?v=1");
const { publishMic, wireOpen } = await import("../../../../frontend/app/services/mic-wire.js?v=1");
const tick = () => new Promise(r => setTimeout(r, 0));

assert.equal(store.micMuted(), true, "the stored switch seeds the signal");
assert.equal(store.micWire(), null, "no session: nothing to ask");
assert.equal(mic.iconOpen(), false, "closed switch, no session: slashed");

// ── 1 · a reconnect publishes the capture already closed ───────────────────────────────────────────────────────────
const order = [];
const capture = { readyState: "live", enabled: true };
class FakeLocal {
  constructor(tr) { this.mediaStreamTrack = tr; this.isMuted = false; order.push(`wrap(enabled=${tr.enabled})`); }
  async mute() { this.isMuted = true; this.mediaStreamTrack.enabled = false; order.push("mute"); return this; }
}
const pubs = new Map();
const enabledAsks = [];
const room = { localParticipant: {
  audioTrackPublications: pubs,
  async publishTrack(lt) {
    order.push(`publish(enabled=${lt.mediaStreamTrack.enabled},muted=${lt.isMuted})`);
    pubs.set("mic", { track: lt, get isMuted() { return lt.isMuted; } });
  },
  async setMicrophoneEnabled(on) {
    enabledAsks.push(on);
    const p = pubs.get("mic"); if (p) { p.track.isMuted = !on; p.track.mediaStreamTrack.enabled = on; }
  },
} };
await publishMic({ track: capture, closed: mic.muted(), wrap: (tr) => new FakeLocal(tr),
                   publish: (lt) => room.localParticipant.publishTrack(lt) });
assert.deepEqual(order, ["wrap(enabled=false)", "mute", "publish(enabled=false,muted=true)"],
  "THE BUG: the capture was published open and muted only afterwards — every frame in between left the browser");
assert.equal(wireOpen(room), false, "born closed: nothing leaves the page");

// the session registers its transport (session-lk.js does exactly this after publishing)
const transport = (want) => { capture.enabled = !want; room.localParticipant.setMicrophoneEnabled(!want); };
posts.length = 0;
mic.useTransport(transport, () => wireOpen(room));
await tick();
assert.ok(!enabledAsks.includes(true), "a closed switch never asks LiveKit for an enabled microphone");
assert.equal(store.micWire(), false);
assert.equal(mic.iconOpen(), false);
assert.ok(posts.some(p => p.url.includes("/api/mic") && p.body && p.body.muted === true),
  "a new transport re-sends the switch: the engine under it may have restarted at its boot default");
await tick();
posts.length = 0;
mic.useTransport(transport, () => wireOpen(room));                         // the next session, same switch
await tick();
assert.ok(posts.some(p => p.url.includes("/api/mic") && p.body && p.body.muted === true),
  "…every time: an unchanged switch is still re-sent to a session that may face a restarted engine");

// ── 2 · the icon is the wire: a sending mic under a closed switch shows OPEN, and the beat closes it ────────────────
pubs.get("mic").track.isMuted = false; capture.enabled = true;            // something reopened the wire behind the door
mic.readWire();
assert.equal(mic.iconOpen(), true, "a sending mic is never drawn closed — the mismatch must be visible");
assert.equal(mic.shownOpen(), true);
posts.length = 0;
assert.equal(mic.beat(), true, "the beat still tells the engine his switch: muted");
assert.equal(wireOpen(room), false, "off wins: the beat closed the wire again");
assert.equal(mic.iconOpen(), false, "…and the icon follows the wire back to closed");
await tick();
assert.ok(posts.some(p => JSON.stringify(p.body || {}).includes("wire_mismatch")),
  "the correction is said, not silent");

// ── 3 · the probe reads the publication itself ─────────────────────────────────────────────────────────────────────
const lp = (pub) => ({ localParticipant: { audioTrackPublications: new Map(pub ? [["m", pub]] : []) } });
const live = (o = {}) => ({ isMuted: false, track: { mediaStreamTrack: { readyState: "live", enabled: true, ...o } } });
assert.equal(wireOpen(lp(live())), true);
assert.equal(wireOpen(lp({ ...live(), isMuted: true })), false, "a muted publication sends nothing");
assert.equal(wireOpen(lp(live({ readyState: "ended" }))), false, "a released device sends nothing");
assert.equal(wireOpen(lp(live({ enabled: false }))), false, "a disabled track sends silence");
assert.equal(wireOpen(lp(null)), false, "captured but unpublished: nothing leaves the page");
assert.equal(wireOpen(null), false);

// ── 4 · faults: slashed with nothing sending, open over a sending mic ──────────────────────────────────────────────
store.setDeviceConds({ mic: { no_agent: "rooms asked, no agent" }, spk: {} });
mic.useTransport(null);
store.setMicMuted(false);
assert.equal(store.micWire(), null);
assert.equal(mic.iconOpen(), false, "no session and a fault: no capture can exist — slashed (red)");
mic.useTransport(() => {}, () => true);
assert.equal(mic.iconOpen(), true, "a fault over a SENDING mic is drawn open: hiding it is the lie");
mic.useTransport(() => {}, () => false);
assert.equal(mic.iconOpen(true), true, "the wake-word park keeps the open glyph (the browser's ear listens)");
store.setMicMuted(true);
assert.equal(mic.iconOpen(true), false, "…never over his closed switch");
store.setDeviceConds({ mic: {}, spk: {} });

console.log("ok — the 🎤 mirrors the wire, and a reconnect is born closed");

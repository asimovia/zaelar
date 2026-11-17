// ============================================================================
// test_the_voice_level_holds_where_the_element_ignores_it.mjs — V2-930 (gain), node 4.573.
//
// iOS WebKit (Safari and the app's WKWebView) ignores `HTMLMediaElement.volume`, so on the phone «volumen al 30 %»
// changed nothing. There the agent's voice leaves through a Web Audio gain (services/audio.js) and the element stays
// silent; everywhere else the element's own volume is still the level. Driven over the REAL `volume.js`, `audio.js`
// and `store.js` with a recorded Web Audio graph. Pinned:
//   • iOS WebKit routes the voice through the gain even though its element READS BACK the volume it ignores (measured on
//     an iPhone, iOS 18.7); a platform that honours the element's volume does not;
//   • routed: the gain carries the level (30 % → 0.3, 100 % → 1) and the 🔊 (muted → 0), the element is held muted
//     even after the vendor un-mutes it, and only ONE route reaches the speakers after a second track;
//   • the route gone (session stop), the element is the way out again, at his level;
//   • a context opened before any touch is resumed by the unlock.
//
// Run: node tests/browser/unit/voice/test_the_voice_level_holds_where_the_element_ignores_it.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
// iOS WebKit as measured (iOS 18.7, WKWebView): an element's volume READS BACK what the page wrote and still plays at
// full, so only the platform gives it away.
let honours = true;
const ua = (s, platform = "", touch = 0) => Object.defineProperty(globalThis, "navigator",
  { configurable: true, value: { userAgent: s, platform, maxTouchPoints: touch } });
ua("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 ZaelarApp/1.1.0 (ios)", "iPhone", 5);
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => { let v = 1; return { get volume() { return v; }, set volume(x) { if (honours) v = x; } }; } };
globalThis.MediaStream = class MediaStream {};

// A recorded Web Audio graph: which nodes reach the destination, and each gain's value.
const toSpeakers = new Set();
let resumed = 0;
class Node_ { constructor(ctx) { this.ctx = ctx; this.out = new Set(); }
  connect(n) { this.out.add(n); if (n === this.ctx.destination) toSpeakers.add(this); return n; }
  disconnect() { for (const n of this.out) if (n === this.ctx.destination) toSpeakers.delete(this); this.out.clear(); } }
class Ctx { constructor() { this.state = "suspended"; this.destination = { kind: "destination" }; }
  createAnalyser() { return Object.assign(new Node_(this), { fftSize: 0 }); }
  createGain() { return Object.assign(new Node_(this), { gain: { value: 1 } }); }
  createMediaStreamSource() { return new Node_(this); }
  resume() { resumed++; this.state = "running"; return Promise.resolve(); }
  close() { this.state = "closed"; } }
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" }, AudioContext: Ctx };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const audio = await import("../../../../frontend/app/services/audio.js?v=2");
const volume = await import("../../../../frontend/app/services/volume.js?v=1");

const gainOut = () => { assert.equal(toSpeakers.size, 1, `exactly one route reaches the speakers: ${toSpeakers.size}`);
                        return [...toSpeakers][0].gain.value; };
const near = (a, b, why) => assert.ok(Math.abs(a - b) < 1e-9, `${why}: ${a} ≠ ${b}`);

// ══ 1 · iOS: the voice leaves through the gain, the element stays silent ═══════════════════════════════════
store.setBotMuted(false);
assert.equal(volume.elementHonoursVolume(), false);
assert.equal(volume.routesOut(), true, "where the element's volume is ignored the voice goes out by the gain");
assert.equal(volume.settable(), true, "and the level CAN be honoured: the screen must not say «follows the buttons»");
audio.initMic(new MediaStream());
const el = { muted: false, volume: 1 };
volume.bind(el);
audio.attachBot(new MediaStream(), volume.routesOut());
assert.equal(audio.botOutRouted(), true);
assert.equal(el.muted, true, "routed, the element is held muted — the voice must come out once");
near(gainOut(), 1, "the default level is full");
volume.setLevel(30);
near(gainOut(), 0.3, "30 % is the gain at 0.3");
volume.setLevel(100);
near(gainOut(), 1, "100 % is full");
volume.setLevel(60);
store.setBotMuted(true);
near(gainOut(), 0, "the 🔊 muted is the gain at 0");
assert.equal(el.muted, true);
store.setBotMuted(false);
near(gainOut(), 0.6, "un-muted, his level again");
// the vendor un-mutes the element on every attach; the session re-holds it on `volumechange`
el.muted = false; volume.enforce(el);
assert.equal(el.muted, true, "a vendor un-mute is reverted while routed");
// a new track (reconnection inside the same context) replaces the route instead of adding a second voice
audio.attachBot(new MediaStream(), volume.routesOut());
near(gainOut(), 0.6, "the new route starts at his level");
// the unlock resumes a context opened before any touch
audio.resumeContext();
assert.equal(resumed, 1, "the gesture's unlock resumes the context the gain plays in");

// ══ 2 · the route gone: the element is the way out again ═══════════════════════════════════════════════════
audio.reset("session_stop");
assert.equal(audio.botOutRouted(), false);
assert.equal(toSpeakers.size, 0, "a stopped session leaves no route behind");
assert.equal(el.muted, false, "with no route the element plays again (un-muted 🔊)");

// ══ 3 · a platform that honours the element's volume keeps it (Chrome: its echo canceller hears the element) ══
honours = true; ua("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/142.0 Safari/537.36", "MacIntel", 0);
const desk = await import("../../../../frontend/app/services/volume.js?v=desk");
assert.equal(desk.routesOut(), false, "where the element's volume works the voice is NOT moved to Web Audio");
assert.equal(desk.settable(), true);
audio.initMic(new MediaStream());
const el2 = { muted: false, volume: 1 };
desk.bind(el2);
audio.attachBot(new MediaStream(), desk.routesOut());
assert.equal(audio.botOutRouted(), false);
assert.equal(toSpeakers.size, 0, "nothing reaches the speakers through Web Audio there");
desk.setLevel(30);
near(el2.volume, 0.3, "the element plays at the level");
assert.equal(el2.muted, false);

// an iPad asking for the desktop site is a touch «MacIntel»: still iOS WebKit
ua("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.7 Safari/605.1.15", "MacIntel", 5);
assert.equal((await import("../../../../frontend/app/services/volume.js?v=ipad")).routesOut(), true, "an iPad is iOS WebKit");
// any other platform whose element reads back deaf goes out by the gain too
ua("Mozilla/5.0 (X11; Linux x86_64)", "Linux x86_64", 0); honours = false;
assert.equal((await import("../../../../frontend/app/services/volume.js?v=deaf")).routesOut(), true, "a deaf read-back routes by the gain");

// ══ 4 · neither: the screen says the level follows the device's buttons ═══════════════════════════════════════
honours = false; delete globalThis.window.AudioContext;
const bare = await import("../../../../frontend/app/services/volume.js?v=bare");
assert.equal(bare.routesOut(), false);
assert.equal(bare.settable(), false, "no Web Audio and an ignored volume: the level cannot be honoured here");

console.log("ok — the voice level holds where the element ignores it");

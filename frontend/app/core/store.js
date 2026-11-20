// ============================================================================
// store.js — app-wide reactive state as signals (the Solid createStore/context
// equivalent). SERVICES write these; COMPONENTS read them via effects. No DOM
// here, no business logic — just the shared state the UI reacts to.
//
// Persisted bits (mic muted, camera off, orb style, voice gate) seed from
// localStorage so the UI reflects the user's last choice before a stream exists.
// ============================================================================
import { createSignal } from "./reactive.js?v=2";

// ---- active UI language (V2-089 multilingual) — the single signal every t() reads. Seeds instantly from the
// localStorage mirror (no flash for returning operators), then initI18n() reconciles against the backend's
// active language (ZAELAR_LANGUAGE). Flipping it re-renders every localized string in the tree, live. ----
export const [lang, setLang]           = createSignal(localStorage.getItem("hb_lang") || "en");

export const [started, setStarted]     = createSignal(false);   // a live session is up
export const [starting, setStarting]   = createSignal(false);   // session is connecting
export const [conn, setConn]           = createSignal({ label: "—", ok: false });
export const [latency, setLatency]     = createSignal("— ms");  // reply time-to-first-audio

// Boot overlay gate: false blocks the UI on first load (agents booting, voice connecting, memory composing). Flips
// true on the room-scoped "ready" signal from the agent, or a safety timeout — see session-lk.js. Stays true across
// later reconnects (only the very first boot blocks).
export const [bootReady, setBootReady] = createSignal(false);
// Boot PHASE — the ordered startup milestones the splash animates through (one cluster of the synaptic
// constellation per phase). Advanced by REAL signals: the frontend reports "voz" (mic + room up); the backend
// reports "memoria"/"reflejo" over the "vl2" data channel; "listo" = init done (ready), just before zaelar greets.
// Single source of truth for both the animation and the caption. See components/boot-anim.js + BootOverlay.js.
export const BOOT_PHASES = ["encendiendo", "voz", "memoria", "reflejo", "listo"];
export const [bootPhase, setBootPhase] = createSignal("encendiendo");

export const [theme, setTheme]         = createSignal(localStorage.getItem("hb_theme") || "dark");  // "dark" | "light" — dark by default (night-friendly)

export const [micMuted, setMicMuted]   = createSignal(localStorage.getItem("hb_mic_muted") === "1");
// What the mic's WIRE is doing (2026-11-18): true = a published capture is sending, false = nothing leaves the page,
// null = no session transport to ask. Written ONLY by `services/mic.js` from the session's own probe; the 🎤 draws this.
export const [micWire, setMicWire]     = createSignal(null);
export const [camOff, setCamOff]       = createSignal(localStorage.getItem("hb_cam_off") === "1");
export const [botMuted, setBotMuted]   = createSignal(localStorage.getItem("hb_bot_muted") === "1");  // silence zaelar's voice OUTPUT (agent keeps running)

// ⏻ POWER (V2-039 «ojo»): EXPLICIT shutdown of the voice session by the operator — the only exception to always-on.
// Persisted: a deliberate shutdown survives refresh; main.js does NOT auto-(re)connect while it is off.
//
// V2-092: this signal is NO LONGER the truth; it is the LOCAL MIRROR of a truth that lives on the server
// (`nucleo/runstate.py`, `GET /api/run`). The reason was the failure that exposed it: with the agent stopped, a video kept
// playing and restarting made it start on its own. With the switch only here, the backend —widgets,
// background, crons— had no one to ask whether the operator had stopped it, and this localStorage is per-browser
// and per-origin: the same zaelar on two ports were two agents with different opinions about whether they were alive.
// Now: ⏻ COMMANDS the server (POST /api/run/stop|start), and the server NOTIFIES (SSE `run`) → all
// tabs converge. localStorage remains for instant startup without waiting for the network.
export const [powerOff, setPowerOffRaw] = createSignal(localStorage.getItem("hb_power_off") === "1");
export const setPowerOff = (off) => { setPowerOffRaw(off); localStorage.setItem("hb_power_off", off ? "1" : "0"); };

// STAMP OF THE OPERATOR'S LAST ⏻ COMMAND (2026-08-14, real failure captured by the operator).
// The server reconciliation in main.js is ASYNCHRONOUS, and on a machine waking from cold it takes seconds.
// If the operator presses ⏻ inside that window, the reply — a snapshot of the state BEFORE the click — landed
// afterwards and set `powerOff` again, tearing down the very session the operator had just asked for. It is the
// classic last-write-wins failure between two clocks: the SLOWEST message won, not the NEWEST one.
// With this stamp the seeding can ask "has the operator commanded anything since I went to fetch this?" and stay
// quiet when the answer is yes. NOT touched by the SSE `run` event: that one IS the server's truth and must win.
export const [powerCmdAt, setPowerCmdAt] = createSignal(0);
export const markPowerCommand = () => setPowerCmdAt(Date.now());

// ⏻ ON IS IN FLIGHT (V2-627, 2026-09-09, measured on the operator's own log): between `setPowerOff(false)` and
// `POST /api/run/start` landing, the server still says STOPPED — and anything that starts the voice session in
// that gap dies against `session-lk.js`'s own ⏻ gate, which reads that stale truth and puts `powerOff` back to
// true. It took TWO presses to turn the agent on. The starter of that ghost session was not the click (Orb.js
// has sequenced `runStart().then(session.start)` since 2026-08-31) but the effect added the SAME day to revive
// the voice when `powerOff` drops from outside this tab: it fires the instant the flag flips, synchronously,
// inside the click itself. Both fixes were right; together they raced.
// While this window is open the ⏻ click OWNS the startup and no other road may open a session. It is a
// TIMESTAMP, not a boolean, so it can never wedge the voice shut: an answer that never comes expires by itself.
export const [powerOnAt, setPowerOnAt] = createSignal(0);
export const markPowerOnPending = () => setPowerOnAt(Date.now());
export const clearPowerOnPending = () => setPowerOnAt(0);
export const powerOnPending = () => { const t = powerOnAt(); return t > 0 && (Date.now() - t) < 15000; };

// ⏻ PAUSING (V2-092 addenda, 2026-08-15): a stop requested while a turn's model call is REALLY in flight
// (`nucleo/runstate.py`'s `_inflight`) doesn't cut anything mid-way — it's DEFERRED until that turn ends on its
// own, never on a timer. Meanwhile the agent keeps genuinely running underneath (nothing has been frozen): this
// is just the signal for ⏻ to show that (amber blink) instead of lying by painting itself already off. Set by
// the `run` SSE event (label "pausing"/"resumed") — reaches EVERY tab alike, whether or not it clicked ⏻.
export const [pausing, setPausing] = createSignal(false);

export const [botSpeaking, setBotSpeaking] = createSignal(false);            // gates person-voice visuals
export const [micBlocked, setMicBlocked]   = createSignal({ show: false, msg: "" });
// Another tab or a remote driver holds the single voice session (V2-776, 2026-09-27): this tab is not broken,
// it is being CONTROLLED FROM ELSEWHERE, and the ⏻ says so in blue instead of the amber of a fault.
export const [remoteHeld, setRemoteHeld] = createSignal(false);  // 🚫 ring over the orb
// The engine went to sleep (`engine.sleep`, services/presence.js): `face` "sleep" darkens the whole screen
// (components/Veil.js) and `waking` says a gesture asked it back and the stream has not answered yet.
export const [dormant, setDormant] = createSignal({ face: "", waking: false });
export const [micLevel, setMicLevel]       = createSignal(0);               // true mic RMS (0..1) for the meter

// ── attention gate (V2-016 + 2026-09-09): the 🤖 mode + a real-time "I'm listening to YOU" ring ─────────────
// `attentionMode` mirrors config/settings.json's `attention_mode` (source of truth: /api/settings on load,
// then the `ui`/`orb:attention` SSE event whichever side changes it — the button OR a voice order, see
// nucleo/flash/identity_actions.py). `assistantName` is the CURRENT spoken name (renamed via voice), read the
// same way + `ui`/`orb:name`. `attentionHit` lights the ring the instant the gate judges a turn DIRECTED —
// the only real-time signal this turn-based system can give (never word-by-word); it clears on the next
// `ambient` (not-directed) verdict or after its own `window_s`, whichever comes first — see sse.js.
export const [attentionMode, setAttentionMode] = createSignal("always");
export const [assistantName, setAssistantName] = createSignal("Johnny");   // until GET /api/settings answers: the genome's default name (V2-929)
export const [attentionHit, setAttentionHit]   = createSignal(false);
let _attnHitT = null;
export function pulseAttentionHit(windowS) {
  setAttentionHit(true);
  clearTimeout(_attnHitT);
  _attnHitT = setTimeout(() => setAttentionHit(false), Math.max(1, Number(windowS) || 30) * 1000);
}
export function clearAttentionHit() { clearTimeout(_attnHitT); setAttentionHit(false); }

// ── IS THE AGENT ALIVE? ONE single derived answer — not another signal to maintain ────────────────────────
// It arose from a real and costly failure (operator session, 2026-08-10). Each orb icon decided its appearance from
// a DIFFERENT signal, and none meant «the agent is running»:
//   · `powerOff` is the operator's persisted INTENTION, not reality;
//   · `started` is reality, but nobody checked it for rendering.
// With `powerOff=false` and the session DOWN (microphone denied, room lost, a startup failure), the mic,
// speaker, and ⏻ were still rendered blue. The operator spent quite a while talking to a dead agent: «because
// I saw the microphone on, the speaker on, and the transcription on, so I thought you were
// I saw the microphone on, the speaker on, and the transcription on, I thought you were operational». It was not
// an audio failure: it was an invisible state.
//
// Five states — the fifth (V2-092 addenda, 2026-08-15) is ANOTHER transition, not a made-up state: a stop
// requested with a turn in flight that the server defers until it ends on its own (see `pausing` above). It goes
// BEFORE `off` on purpose: underneath, the agent keeps genuinely running while it lasts, so painting it already
// off would be the same visual lie that `stalled` exists to correct.
//   pausing  → stop requested, waiting for the in-flight turn to end (or for the operator to cancel it).
//   off      → the operator stopped it (⏻). Everything must look and be FROZEN.
//   starting → coming up (connecting room/mic). Neither alive nor stopped: in transit.
//   live     → a session REALLY in progress. The only thing that authorizes painting anything as "on".
//   stalled  → should be on and ISN'T. This is the one that didn't exist; now it's visible.
export const agentState = () => {
  if (pausing()) return "pausing";
  if (powerOff()) return "off";
  if (started()) return "live";
  if (remoteHeld()) return "remote";
  // `!bootReady()` covers the STARTUP gap: between the page loading and `session.start()` setting
  // `starting`, nothing has been set yet — without this, every load would open in «stalled» (everything in alarm)
  // for a few moments. `bootReady` is false only on the first startup, so a session that goes down AFTERWARD does
  // fall into «stalled», which is what should be shown.
  if (starting() || !bootReady()) return "starting";
  return "stalled";
};
// The only predicate views should use to decide whether something can be read as «active».
export const agentLive = () => agentState() === "live";

// ── WHAT THIS SCREEN SHOWS (V2-792 §9, operator 2026-10-25) ──────────────────────────────────────────────────
// One agent may be open on several screens; only one holds the voice. Every face of the centre — the desktop eye,
// the desktop bar slot, the phone dock — paints THIS, and none re-derives it from the flags below:
//   off       → the agent is stopped: the grey ⏻.
//   secondary → the agent runs and the voice is on ANOTHER screen: the grey orb with the slashed mic, never orange.
//   speaking  → this screen holds the voice and the agent is talking: the orange orb.
//   holder    → this screen holds the voice and the agent is quiet: the grey orb.
//   starting · stalled · pausing → in transit or fallen, as `agentState` says.
// It exists because «voice elsewhere» used to wear the ⏻ face of «stopped», and pressing it stopped everything.
export const screenState = () => {
  const s = agentState();
  if (s === "remote") return "secondary";
  if (s === "live") return botSpeaking() ? "speaking" : "holder";
  return s;
};

export const [voices, setVoices]       = createSignal([]);
export const [voiceIdx, setVoiceIdx]   = createSignal(0);
export const [voiceFlash, setVoiceFlash] = createSignal({ text: "", show: false });   // transient "🗣 <voice>" label

// ---- live captions (zaelar's speech crawling above the orb) ----
// captionsOn = the 📝 toggle under the orb (default ON). captionSeg = a STREAMING transcription segment from
// LiveKit (RoomEvent.TranscriptionReceived), delivered incrementally IN SYNC with the agent's audio playback —
// { id, text (cumulative for that segment), final }. Seq bumps so the caption component reacts to every update.
// LIVE ONLY — the chat wall keeps the history.
// V2-623 — WHERE THE ORB LIVES: "eye" = the big bottom-centre eye cluster (default); "bar" = a small orb in
// the centre of the bottom system bar, with the eye hidden. Toggled by the lid's corner swap icon and by the
// bar's own centre button; persisted so a reload keeps the shape the operator chose.
export const [orbDock, setOrbDockRaw] = createSignal(localStorage.getItem("hb_orb_dock") === "bar" ? "bar" : "eye");
export const setOrbDock = (v) => { const m = v === "bar" ? "bar" : "eye"; setOrbDockRaw(m); try { localStorage.setItem("hb_orb_dock", m); } catch (_) {} };

// V2-757 — THE ORB STEPS ASIDE ON ITS OWN WHEN SOMETHING GOES FULL-SCREEN. Operator, live session
// f84f91ef (2026-09-23), watching a video full-bleed: «en el frontend se ve el orbe con el pulso, y eso
// molesta cuando estás viendo un vídeo a pantalla completa. Yo creo que automáticamente cuando algo se
// pone en pantalla completa, el orbe tiene que desaparecer y irse a la barra inferior».
//
// It is the dock V2-623 already built, driven by the screen instead of by his hand — and it writes
// through `setOrbDockRaw`, NOT `setOrbDock`, on purpose: this is OUR temporary decision, so it must not
// overwrite the shape he chose. `_before` holds that shape and gives it back on the way out; it is not
// re-entrant on purpose (a second fullscreen while one is up must not record "bar" as his preference).
let _dockBeforeFullscreen = null;
export const orbDockForFullscreen = (on) => {
  if (on) {
    if (_dockBeforeFullscreen === null) _dockBeforeFullscreen = orbDock();
    setOrbDockRaw("bar");
  } else if (_dockBeforeFullscreen !== null) {
    const back = _dockBeforeFullscreen;
    _dockBeforeFullscreen = null;
    setOrbDockRaw(back);
  }
};

export const [captionsOn, setCaptionsOn] = createSignal(localStorage.getItem("hb_captions_on") !== "0");
export const [captionSeg, setCaptionSeg] = createSignal(null);
let _capSeq = 0;
export const pushCaptionSeg = (id, text, final) => {
  setCaptionSeg({ id, text: text || "", final: !!final, seq: ++_capSeq });
};
export const toggleCaptions = () => {
  const next = !captionsOn(); setCaptionsOn(next); localStorage.setItem("hb_captions_on", next ? "1" : "0");
  return next;
};

export const [orbStyle, setOrbStyle]   = createSignal(localStorage.getItem("zaelar_orb") || "pro");  // "pro" | "friendly"
export const [gateOn, setGateOn]       = createSignal(localStorage.getItem("zaelar_gate") === "1");  // speaker filter (opt-in)
export const [spk, setSpk]             = createSignal({ show: false, text: "", kind: "" });           // owner-voice indicator

export const [alert, setAlert]         = createSignal(null);   // { msg, onClick } | null  → top banner
// A BLOCKING FAULT — the agent cannot work and saying so quietly is not enough (V2-676).
//
// The operator, after a session where the model ran out of credit mid-conversation and the only sign was a
// sentence spoken in the wrong language: «la voz hay que pararla y hay que bloquear a la gente… que salga la
// alerta en grande… en el idioma del usuario, obviamente… y ponemos un botón que abra la configuración».
//
// It holds FACTS from the engine (`{code, model, provider, suppressed, config_key}`), never prose: the text is
// rendered here from i18n keys, so a French install shows French — which a sentence composed by the engine
// could not do, because the thing that translates is the very model that just died.
export const [fault, setFault]         = createSignal(null);   // { code, model, provider, suppressed, config_key } | null
export const showFault = (f) => setFault(f && typeof f === "object" ? f : { code: "no_model_credit" });
export const clearFault = () => setFault(null);

// AUDIO PLAYBACK BLOCKED BY THE BROWSER (V2-573). Not a mute and not a failure: every mobile browser refuses to
// play a remote audio track until the page has had a user gesture, and LiveKit reports it as `canPlaybackAudio`.
// It is a SIGNAL rather than only an alert because on a phone it must be visible on the control the operator is
// already looking at (the orb) — an operator who cannot hear the agent looks at the orb, not at a banner they may
// have already dismissed.
export const [audioBlocked, setAudioBlocked] = createSignal(false);

// DEVICE HEALTH (V2-788). Mid-session the agent's voice stopped being heard while the engine kept synthesising,
// and the browser had reported nothing since connect: no way to tell a paused element from a dead track, a lost
// output device or a silent stream. `services/device-health.js` is the only writer of `deviceConds` — the raw
// conditions each detector saw, per device — and the two functions below are the ONE derived verdict each icon
// reads. A deliberate mute is not a fault: it explains every condition except the ones listed as surviving it
// (a mute does not explain a revoked permission). Conditions in WHILE_SPEAKING only count while the engine says
// the agent is speaking — a remote track the browser flags as muted between utterances is just silence.
// `blocked` is not stored here: it IS `audioBlocked`, the SDK's own verdict, read directly so there is one door.
// `no_agent` (2026-11-16) is not the device: it is the far end of the same wire — rooms asked for and none joined by
// the agent. To the person it is the same fact («nobody hears me»), so it paints the mic, and no mute explains it.
export const DEVICE_PROBLEMS = {
  mic: ["permission_denied", "no_device", "capture_error", "track_ended", "track_muted", "no_agent"],
  spk: ["blocked", "track_ended", "element_error", "paused", "context_interrupted", "no_output", "sink_lost",
        "silent_while_speaking", "remote_muted"],
};
const _SURVIVES_MUTE = { mic: ["permission_denied", "no_device", "no_agent"], spk: [] };
const _WHILE_SPEAKING = ["remote_muted"];
export const [deviceConds, setDeviceConds] = createSignal({ mic: {}, spk: {} });
export const deviceHealth = (device) => {
  const conds = { ...((deviceConds() || {})[device] || {}) };
  if (device === "spk" && audioBlocked()) conds.blocked = "canPlaybackAudio=false";
  const muted = device === "mic" ? micMuted() : botMuted();
  for (const reason of DEVICE_PROBLEMS[device] || []) {
    if (!(reason in conds)) continue;
    if (muted && !_SURVIVES_MUTE[device].includes(reason)) continue;
    if (_WHILE_SPEAKING.includes(reason) && !botSpeaking()) continue;
    return { ok: false, reason, detail: String(conds[reason] || "") };
  }
  return { ok: true, reason: "", detail: "" };
};
export const micHealth = () => deviceHealth("mic");
export const spkHealth = () => deviceHealth("spk");

// ---- proactive notifications (orchestrator loop / scheduled task fired → zaelar reaches out) ----
// No floating toast: a proactive push surfaces as a live caption over the orb + a chat-wall entry (see sse.js).

// ---- background activity indicators (liquid blobs FLANKING the orb, left & right) ----
// Every in-flight SlowBrain task (widget build/modify, web task, memory, deep reasoning) becomes ONE liquid blob +
// a short gerund label ("Creando un widget…") placed in a PRECISE zone to the LEFT or RIGHT of the orb — never on
// top of the orb, the captions above it, or the connection line at the bottom-left (that scattered-everywhere
// layout was the operator's complaint). New tasks alternate sides (balance left↔right) and STACK vertically inside
// their zone. Fed by SSE "task" events (kind "task", label start/end) from nucleo/dispatch.py. Side + breathing
// phase are frozen at start so the blob doesn't jump on re-render. On end it flashes "done", then clears.
// NOT a floating toast — it's ambient background-activity, no message content, tied to the canvas.
// V2-608 F7 — a task carries TWO texts, because they answer two different questions and only one of them may
// move. `title` is the errand's NAME (V2-530: a fragment of the dialogue, the same name the flow board and the
// worker share) — it is what the «Procesos» row is ABOUT, and it must hold still. `note` is what the worker is
// doing right now (phase / progress / plan) and changes every few seconds. They used to be ONE `text` field that
// every writer overwrote in turn, so the operator watched the row's TITLE mutate through «leyendo brickset.com…»
// and progress reports until the updates happened to stop — «no entiendo por qué el título ha ido cambiando».
export const [tasks, setTasks] = createSignal([]);   // [{ id, title, note, pct, startedAt, done, waiting, paused, side, delay, hue }]
export const startTask = (id, title) => setTasks(xs => {
  // A settled name never downgrades back to the brief: the 🏷️ naming event can land before `start` does on a
  // reconnect, so an existing title wins over the one this event carries.
  if (xs.some(t => t.id === id)) return xs.map(t => t.id === id ? { ...t, title: t.title || title || "", done: false } : t);
  const live = xs.filter(t => !t.done);                   // balance across the two zones by ACTIVE count
  const onLeft = live.filter(t => t.side === "l").length;
  const onRight = live.filter(t => t.side === "r").length;
  const side = onLeft <= onRight ? "l" : "r";             // fill the emptier side first (ties → left)
  const delay = -(Math.random() * 3).toFixed(2);          // desync the slow breathing so they don't pulse in unison
  const hue = Math.round((Math.random() * 2 - 1) * 38);   // ±38° hue-rotate → each blob a slightly different tint
  return [...xs, { id, title: title || "", note: "", startedAt: Date.now(), done: false, side, delay, hue }];
});
// The errand got its NAME (dispatch names it once, in the background — «🏷️ encargo nombrado»). This is the only
// writer allowed to REPLACE a non-empty title.
export const retitleTask = (id, title) => setTasks(xs => {
  if (!title) return xs;
  if (!xs.some(t => t.id === id)) return [...xs, { id, title, note: "", startedAt: Date.now(), done: false, side: "l", delay: 0, hue: 0 }];
  return xs.map(t => t.id === id ? { ...t, title } : t);
});
// Live activity (phase / declared plan). Touches `note`, NEVER `title`. Creates the row if the lifecycle events
// arrived out of order (a phase can beat `start` across a reconnect) — that was the old `startTask(phase)` call's
// one legitimate job, and the reason the title kept changing was that it did the rest of it too.
export const noteTask = (id, note) => setTasks(xs => {
  if (!xs.some(t => t.id === id)) return [...xs, { id, title: "", note: note || "", startedAt: Date.now(), done: false, side: "l", delay: 0, hue: 0 }];
  return xs.map(t => t.id === id ? { ...t, note: note || t.note, done: false } : t);
});
export const endTask = (id) => {
  setTasks(xs => xs.map(t => t.id === id ? { ...t, done: true } : t));   // settle to a solid teal dot…
  setTimeout(() => setTasks(xs => xs.filter(t => t.id !== id)), 1100);   // …then it clears
};
// V2-059: STRUCTURED progress from the brain worker → note + step/% (pct −1 = unknown). Idempotent create.
export const setTaskProgress = (id, note, pct, done, total) => setTasks(xs => {
  const tag = (total ? `${Math.min(done || 0, total)}/${total}` : "");
  const clean = (note || "").trim();
  if (!xs.some(t => t.id === id)) return [...xs, { id, title: "", note: clean, startedAt: Date.now(), done: false, side: "l", delay: 0, hue: 0, pct, stepTag: tag }];
  return xs.map(t => t.id === id ? { ...t, note: clean || t.note, pct, stepTag: tag } : t);
});
// V2-038: RECONCILE the chips against the TRUTH (GET /api/tasks reads the server's RAM record). Upon (re)connecting,
// a server restart/crash may have left orphaned chips (a killed task that never emitted `end`) → here we
// drop those that no longer exist and mark `waiting` for the one awaiting the operator's response. End of the disconnected piece.
// 2026-08-18: also FILTER by `status` instead of assuming everything received is alive. The server no longer sends completed tasks
// (`dispatch.active_sessions` filters them), but this side cannot depend on that: every row entering here is rendered «in progress»,
// so a leaked `done` would resurrect the ghost chip we had just fixed — and would also COVER its own ✓ history row (ChatWall
// discards from history the ids that are alive). Two guards for the same truth, on both sides of the seam.
// V2-728 — the field is `state` (the task vocabulary) where it used to be `status` (the worker's). Keeping
// the OLD name working matters: the SSE path and an older server both still speak it, and a guard that
// silently stopped recognising a state would pass everything through — which is the ghost chip this line
// exists to stop, reintroduced by a rename.
const _LIVE_STATES = new Set(["pending", "running", "waiting", "queued"]);
const _isLive = (s) => {
  if (!s) return true;
  const st = s.state || s.status;
  return !st || _LIVE_STATES.has(st);
};
// The START, from whichever of the two shapes arrived. The durable row (V2-728) carries `started_at` in
// epoch SECONDS; the old RAM projection carried `age_s`, an elapsed count. Both still reach here — the
// route answers the first, an SSE-built chip neither — so this is the ONE place that reads the hour.
const _startedAt = (s, fallback) => {
  if (s && typeof s.started_at === "number" && s.started_at > 0) return s.started_at * 1000;
  if (s && typeof s.age_s === "number" && s.age_s >= 0) return Date.now() - s.age_s * 1000;
  return fallback;
};
// A live row answers to TWO ids: its durable `id` (the board, V2-728) and the per-process `session` id every SSE
// `task` event carries. Keyed on one only, the chip an event made and the chip a reconcile made were two chips for
// one task — the bar said «4» over a list of one, and a task's `end` cleared only one of its twins (demo
// 2026-10-22). The session id comes first: it is what the events that follow will name.
const _idsOf = (s) => [s && s.session, s && s.id].filter(v => v !== undefined && v !== null && v !== "").map(String);
export const reconcileTasks = (sessions) => {
  const rows = (sessions || []).filter(_isLive);
  const live = new Map();
  for (const s of rows) for (const k of _idsOf(s)) if (!live.has(k)) live.set(k, s);
  setTasks(xs => {
    // preserve/update the live ones; mark done (→ clear) those no longer in the truth — and ONE chip per row: twins
    // left by an earlier reconcile (one per id) collapse onto the first, the one the events name.
    const ids = new Set(xs.map(t => String(t.id)));
    const seen = new Set();
    const kept = xs.filter(t => {
      if (t.done) return true;
      const s = live.get(String(t.id));
      if (!s) return false;
      const first = _idsOf(s).find(k => ids.has(k));      // the chip the events name, when it exists
      if (seen.has(s) || String(t.id) !== first) return false;
      seen.add(s);
      return true;
    }).map(t => {
      const s = live.get(String(t.id));
      // The server is the one that knows the settled NAME (`title`, V2-530) and the real start (`age_s`) —
      // a chip created from an SSE event mid-flight only knows when IT first heard of the task.
      // Precedence: the server's settled NAME → the name this side already holds → the brief as last resort.
      // `s.goal` before `t.title` would let a server row that has not named the errand yet CLOBBER the name the
      // 🏷️ event already delivered — caught by the mounted test before it shipped.
      return s ? { ...t, title: s.title || t.title || s.goal, note: s.phase || s.note || t.note,
                   startedAt: _startedAt(s, t.startedAt), internal: s.visible === false,
                   waiting: (s.waiting_on === "user" || (s.state === "waiting" && s.waiting_for !== "reply")), reply: s.waiting_for === "reply", paused: !!s.paused } : t;
    });
    const known = new Set(kept.map(t => String(t.id)));
    const added = [];
    let i = kept.filter(t => !t.done).length;
    for (const s of rows) {
      const ids = _idsOf(s);
      if (!ids.length || ids.some(k => known.has(k))) continue;
      const id = ids[0];
      known.add(id);
      added.push({ id, title: s.title || s.goal || "", note: s.phase || s.note || "", done: false,
                   startedAt: _startedAt(s, Date.now()), internal: s.visible === false,
                   side: (i++ % 2 === 0) ? "l" : "r", delay: 0, hue: 0,
                   waiting: (s.waiting_on === "user" || (s.state === "waiting" && s.waiting_for !== "reply")), reply: s.waiting_for === "reply", paused: !!s.paused });
    }
    return [...kept, ...added];
  });
};
export const fetchTasks = async () => {
  try {
    // V2-728 — the route answers `tasks` (a durable row per commission) where it used to answer `sessions`
    // (a RAM projection plus errand rows synthesised beside it). The chips still want only what is LIVE, so
    // this asks for that scope and nothing else; the other three feed the ChatWall's own sub-tabs below.
    const r = await fetch("/api/tasks?scope=live", { cache: "no-cache" });
    const d = await r.json();
    reconcileTasks(d.tasks || []);
  } catch (_) {}
};

// V2-822 — THE number of running processes, ONE reading for every screen that shows it (the desktop's bar and the
// phone's dock): his commissions that are alive, never the engine's internal ones and never a chip settling after
// its end. The chips come from the engine's live board (`/api/tasks?scope=live`, the same rows the processes panel
// lists) and move with its SSE `task` events; `reconcileTasksSoon` re-reads that board when a process starts or
// ends, so an event-built chip (which cannot know whether its task is internal) never inflates the count.
export const liveProcesses = () => (tasks() || []).filter(x => !x.done && !x.internal);
export const liveProcessCount = () => liveProcesses().length;
let _reconcileTimer = null;
export const reconcileTasksSoon = () => { clearTimeout(_reconcileTimer); _reconcileTimer = setTimeout(fetchTasks, 400); };

// V2-822 — a running process MOVED (a line, a declared plan, a step done, the page its browser is on). Bumped by
// every SSE `task` event that names one; the processes panel's entries re-read their ONE record when it moves
// (components/ProcessEntry.js). A counter, not data: the record lives on the server and is never copied here.
export const [processRev, setProcessRev] = createSignal(0);
export const bumpProcess = () => setProcessRev(n => n + 1);

// V2-728 — the FOUR lists behind the «Procesos» tab. One signal each rather than one shared list filtered four
// ways: they are four different queries against the table (live · finished · recurring · scheduled) with
// different lifetimes, and a single cache would make switching sub-tabs show the previous one's rows for a
// frame. `taskShowAll` is the `⚙ todo` switch — it adds the engine's internal escalations, which the operator
// needs while testing by hand and never otherwise.
export const [taskRows, setTaskRows]   = createSignal({ live: [], done: [], recurring: [], scheduled: [] });
export const [taskScope, setTaskScope] = createSignal("live");
export const [taskShowAll, setTaskShowAll] = createSignal(false);
export const fetchTaskScope = async (scope) => {
  const sc = String(scope || "live");
  try {
    const q = "/api/tasks?scope=" + encodeURIComponent(sc) + (taskShowAll() ? "&all=1" : "");
    const r = await fetch(q, { cache: "no-cache" });
    const d = await r.json();
    setTaskRows(x => ({ ...x, [sc]: Array.isArray(d.tasks) ? d.tasks : [] }));
  } catch (_) {}
};

// V2-079 → V2-728: FINISHED commissions — the «Hechas» sub-tab. It used to come from a 50-entry JSON blob
// («the worker ledger»); it is the same durable table the live list reads, so the two cannot disagree about
// whether something ended. Refreshes when the tab opens and when a task ends (SSE task:end).
export const [workerHistory, setWorkerHistory] = createSignal([]);  // [{id,kind,goal,status,finished_at,...}]

// CURRENT WORK SESSION (2026-08-10). A deliberate Reset opens a NEW session in the backend
// (voice/observer.py::rotate_session: new id + observability reset to zero). This counter rises on every RESET and is the
// signal used by IMPERATIVE views —the observability column, which renders its rows manually and does not re-render
// from data— to clear themselves. Without it, after a Reset the panel kept showing rows from the previous session: the
// backend had started blank while the screen had not, the worse of the two possible lies.
export const [sessionEpoch, bumpSessionEpoch] = createSignal(0);
export const newSession = () => bumpSessionEpoch(n => n + 1);
export const fetchWorkerHistory = async () => {
  try {
    // One door. `/api/workers/history` and the `sys_kv` ledger behind it were retired with V2-728 F2; this
    // is the same query the live sub-tab makes, with another scope.
    const r = await fetch("/api/tasks?scope=done", { cache: "no-cache" });
    const d = await r.json();
    setWorkerHistory(Array.isArray(d.tasks) ? d.tasks : []);
  } catch (_) {}
};

// V2-086: CLUSTER CONNECTIONS — native, ChatWall's 4th tab. The network (MeshKore today; perhaps other providers
// tomorrow) is system infrastructure, not a user widget: that is why it lives alongside Processes and Crons and
// NOT in the catalog. Lists clusters for which CREDENTIALS exist (connected or not), with their status and traffic.
// Deliberately WITHOUT conversation: clusters have their own monitor; this only manages the connection.
export const [clusters, setClusters] = createSignal([]);  // [{name,connected,handle,online[],public,msgs,...}]
export const fetchClusters = async () => {
  try {
    const r = await fetch("/api/meshkore/status", { cache: "no-cache" });
    const d = await r.json();
    setClusters(Array.isArray(d.clusters) ? d.clusters : []);
  } catch (_) { setClusters([]); }
};
// Yes/No confirmation to CONNECT to a cluster (V2-086). It lives here and renders in the «Clusters» tab because the
// network is not a canvas card. The gate is deterministic and CANNOT be bypassed: no matter how convincing a pasted
// block of text is, no socket opens without an explicit «yes» from the operator.
// V2-518 — pending WIDGET confirmation (delete / restore / irreversible data-op), mirrored into the chat
// thread per the house norm: no popups — a question renders IN the conversation with Yes/No, answerable
// there or by voice. Fed by the same SSE "confirm"/"confirm-cancel" events that paint the card overlay.
export const [widgetConfirm, setWidgetConfirm] = createSignal(null);     // {id, question, action} | null
export const widgetConfirmResolve = async (ok) => {
  const c = widgetConfirm(); setWidgetConfirm(null);
  if (!c) return;
  try { await fetch(`/widgets/${c.id}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ ok: !!ok }) }); } catch (_) {}
};

export const [clusterConfirm, setClusterConfirm] = createSignal(null);   // {question} | null
export const clusterConfirmResolve = async (ok) => {
  setClusterConfirm(null);
  try { await fetch("/api/meshkore/confirm", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ ok: !!ok }) }); } catch (_) {}
  await fetchClusters();
};
export const clusterConnect = async (name) => {
  try { await fetch("/api/meshkore/connect", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ name }) }); } catch (_) {}
  await fetchClusters();
};
export const clusterDisconnect = async (name) => {
  try { await fetch("/api/meshkore/disconnect", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ name }) }); } catch (_) {}
  await fetchClusters();
};

// ---- memory map (🧠 the "map of zaelar's memory": state + short/long term + concept graph, V2-014) ----
// memOpen = the 🧠 icon in the orb bowl toggles the full-screen visualizer. memBump increments on every
// `memory.updated` SSE push (bridged from the bus in server/__init__.py) so the map refetches LIVE, no polling.
// Full-screen configuration (V2-043): choose API/model per component + API balance summary. Opened by ⚙.
export const [configOpen, setConfigOpen] = createSignal(false); // config area overlay visible?
// V2-561 — which of ConfigPanel's OWN tabs to land on the next time it opens (its tab state is a private
// closure variable, not store-backed: there was no way from outside to say "open on Conectores"). Consumed
// ONCE by ConfigPanel's own open-effect and cleared right after, so it never sticks past the request that
// asked for it — a stale value here would keep re-forcing the tab on every later ⚙ click.
export const [configInitialTab, setConfigInitialTab] = createSignal(null); export const [configInitialSection, setConfigInitialSection] = createSignal(null);   // the section: «open the voice settings»
// The connector the ChatWall catalog was clicked on — ConfigPanel opens on that one alone (consumed once).
export const [configConnector, setConfigConnector] = createSignal(null);
// WHO sent the person to that connector (a card's name, e.g. «Contactos»), or "" when unnamed. Consumed with
// configConnector: its «Volver» goes back THERE (closes the panel) instead of to the connectors list.
export const [configFrom, setConfigFrom] = createSignal(null);
export const [apiSummary, setApiSummary] = createSignal([]);     // [{key,enables,set,state,detail,balance?}] — saldos
export const [apiAlerts, setApiAlerts]   = createSignal([]);     // warn/error subset for the status dialog

export const [memOpen, setMemOpen]     = createSignal(false);  // memory map overlay visible?
export const [memBump, setMemBump]     = createSignal(0);      // ticks on each memory.updated (real-time refresh)
export const bumpMemory = () => setMemBump(n => n + 1);

// ---- feedback widget (V2-099: floating "send feedback to the developers" launcher + panel) ----
export const [feedbackOpen, setFeedbackOpen] = createSignal(false);         // panel visible?
export const [feedbackTab, setFeedbackTab]   = createSignal("new");        // "new" | "sent"
export const [feedbackItems, setFeedbackItems] = createSignal([]);         // [{id,message,status,reply_text,created_at}]
export const [feedbackSending, setFeedbackSending] = createSignal(false);  // POST in flight?
// Live observability (V2-014): the latest memory pulse {op, ids} — per-node tint (write=green,
// overwrite=amber, query=blue). Separate from memBump so a query (no data change → no refetch) still tints.
export const [memPulse, setMemPulse]   = createSignal(null);
export const pushMemPulse = (ev) => setMemPulse(ev);

// ---- language onboarding (V2-101): first-run blocking modal — "ask" (English question, voice or quick-pick) →
// "detected" (translated loading line while the full bundle/alias-pack generate) → "ready" (unblocks). Gated
// open by main.js reading GET /api/i18n/state's `chosen` field once bootReady() flips; closed by the "ready"
// SSE phase. Never reopened once closed — a returning operator switching language via ⚙ does NOT go through
// this (that path already applies live without blocking anything).
export const [langOnboardOpen, setLangOnboardOpen]   = createSignal(false);
export const [langOnboardPhase, setLangOnboardPhase] = createSignal("ask");   // "ask" | "detected" | "ready"
export const [langOnboardLoading, setLangOnboardLoading] = createSignal(""); // translated onboarding.loading text
// V2-672 — the handful of strings the first-run modal paints BEFORE the full bundle exists (the loader line
// and the folder step's own words). They ride the same SSE "detected" event, already translated by
// i18n/init/detect.py's priority pass, because everything the operator sees after choosing a language has
// to be in that language — including the screen that runs WHILE the rest of it is being generated.
export const [langOnboardStrings, setLangOnboardStrings] = createSignal({});
// Something in the first-run flow is still holding the veil open. It started as one fact (the folder
// question is unanswered) and is now a SET OF REASONS, because there is more than one thing that can be
// true at once and whoever releases one must not release the others. The language being ready is not
// enough to close: a bundle finishing while somebody is half-way through choosing a folder must not take
// the question off the screen, and the same bundle finishing 200 ms after the loader appeared must not
// take the loader off the screen before anybody has read it.
export const [langOnboardHold, setLangOnboardHold] = createSignal(false);
const _langHolds = new Set();
let _langReady = false;

// V2-731 — how long the preparing screen stays up, at minimum, once it has appeared. The operator, after
// choosing a language: «ha salido como una pequeña pantalla que ha durado un segundo o dos y no sé qué
// era… como mínimo debe durar dos segundos para que la gente lo vea». For a preset language `prepare()` is
// instant, so "detected" and "ready" land back to back and the screen was a flicker with no information
// in it. A screen nobody can read is a screen that did not happen.
export const LANG_LOADER_FLOOR_MS = 2200;
let _floorArmed = false;

// How far the preparation has got: {done, total} from the server's own steps, or null when it has not said
// (an older engine, or the event lost) — the bar is indeterminate then rather than inventing a number.
export const [langOnboardProgress, setLangOnboardProgress] = createSignal(null);

// Is there anything to WATCH? False for a language that is already initialized — the engine says so by
// counting zero steps — and then no preparing screen is drawn at all and no floor is armed. The operator,
// after V2-731 showed him one for two seconds with nothing behind it: «si no hay que hacer nada para
// idiomas inicializados, mejor no mostrar NADA en ese caso». The floor is for a wait that is real.
export const [langOnboardPreparing, setLangOnboardPreparing] = createSignal(false);

function _maybeCloseLangOnboard() {
  if (!_langReady || langOnboardHold()) return;
  // let the CSS fade (.gone) play, then unmount — and look AGAIN when the timer fires: a hold taken during
  // the fade (the folder question) must keep the veil up, or a scheduled close skips the step it guards.
  setTimeout(() => { if (_langReady && !langOnboardHold()) setLangOnboardOpen(false); }, 550);
}

export function requestLangOnboardClose() {
  _langReady = true;
  _maybeCloseLangOnboard();
}

export function holdLangOnboard(on, reason = "step") {
  if (on) _langHolds.add(reason); else _langHolds.delete(reason);
  setLangOnboardHold(_langHolds.size > 0);
  if (!on) _maybeCloseLangOnboard();
}

/** The preparing screen just appeared: hold the veil for its floor, whatever else happens. Idempotent —
 *  a second "detected" (a retry, a reconnect) must not restart the clock the operator is already watching. */
export function beginLangOnboardLoading() {
  if (_floorArmed) return;
  _floorArmed = true;
  holdLangOnboard(true, "floor");
  setTimeout(() => holdLangOnboard(false, "floor"), LANG_LOADER_FLOOR_MS);
}

// ---- MOBILE SHELL (V2-124) — signals owned by the mobile PWA shell (frontend/mobile/), never read by the
// desktop. They live HERE, in the shared store, and not in a store of their own, for the reason that governs the
// whole mobile split: there is ONE truth about this agent. Power, energy, chat, tasks and language are already
// here and both shells read the same signals; a second store would be a second truth, and a state that can lie
// is the failure this codebase has paid for more than once. These three are simply the surfaces that only exist
// on a phone — the desktop has a top bar and a floating launcher instead of a bottom menu.
export const [mobileMenuOpen, setMobileMenuOpen]         = createSignal(false);   // ☰ sheet: account · profile · feedback · settings
export const [mobileSettingsOpen, setMobileSettingsOpen] = createSignal(false);   // the small settings sheet, opened FROM the menu
// The phone's feedback form (inline in MenuSheet), opened from its row OR from the dock's feedback button.
export const [mobileFeedbackOpen, setMobileFeedbackOpen] = createSignal(false);

// ---- secret vault (V2-060): NATIVE modal (create/unlock by passphrase or passkey; show the value) ----
export const [vaultOpen, setVaultOpen]       = createSignal(false);
export const [vaultMode, setVaultMode]       = createSignal("unlock");   // "create" | "unlock" | "reveal" | "manage"
export const [vaultStatus, setVaultStatus]   = createSignal({ exists: false, unlocked: false, methods: [], secret_count: 0 });
export const [vaultPendingMid, setVaultPendingMid] = createSignal(null); // secret to show after unlocking
export const [vaultRevealed, setVaultRevealed] = createSignal(null);     // { label, value } after revealing (ephemeral)
export const [vaultMsg, setVaultMsg]         = createSignal("");         // message/status inside the modal
// opens the modal in a mode; opts.mid = secret pending display after unlocking
export const openVault = (mode, opts = {}) => {
  setVaultMode(mode || "unlock");
  setVaultPendingMid(opts.mid != null ? opts.mid : null);
  setVaultRevealed(null); setVaultMsg("");
  setVaultOpen(true);
};
export const closeVault = () => { setVaultOpen(false); setVaultRevealed(null); setVaultPendingMid(null); setVaultMsg(""); };

// ---- heartbeat / ECG (V2-039): the orb's ELECTROCARDIOGRAM. `pulse` beats on every beat arriving via SSE — a
// `loop.tick` REAL from the orchestrator loop (~1 Hz at rest = the server's own heartbeat, checking crons/processes)
// or the completion of a FlashBrain turn (a higher QRS spike). The Ecg component reads it + tasks()/botSpeaking()
// for the RHYTHM (slow and regular at rest; faster with tasks/turns running). Fed by sse.js. seq forces
// reactivity on every beat even when the payload repeats.
export const [pulse, setPulse] = createSignal(null);
let _pulseSeq = 0;
export const pushPulse = (ev = {}) => setPulse({ ...ev, seq: ++_pulseSeq });

// ---- HARD reset confirmation (TopBar Reset button) ----
// Reset is destructive (stops all background processes + freezes current work in the state memory),
// so it requests confirmation before triggering session.resetHard(). true = dialog visible.
export const [resetConfirmOpen, setResetConfirmOpen] = createSignal(false);
// V2-063: reset with checkboxes (Memory/Credentials) — the server restarts itself; true while we wait
// for it to respond again, so we render a "restarting…" overlay instead of leaving the app in a broken state.
export const [restarting, setRestarting] = createSignal(false);

// ---- first-start wizard (local/cloud profiles + capability detector, V2-040). It opens automatically on the
// first startup (unvalidated config) and can be reopened from the TopBar (🧭). ----
export const [wizardOpen, setWizardOpen] = createSignal(false);

// ---- CLOUD profile: when cloud_profile is set (from /api/config, = ZAELAR_USER_ID set), the header is
// reduced to theme + profile; in self-host it is always false and the header does not change (zero regression). main.js seeds it
// al arrancar desde /api/config. `null` = not known yet: the header renders NOTHING until the engine says which
// profile it is, so a cloud page never flashes the local header first. ----
export const [cloudProfile, setCloudProfile] = createSignal(null);         // cloud account? null = unknown yet
export const [accountOpen, setAccountOpen]   = createSignal(false);        // account panel (profile icon, cloud only)

// ---- ENERGY BALANCE (the top-bar BATTERY, cloud only). `known:false` = we do not know the balance yet, which is
// NOT the same as zero: the battery renders dimmed, never empty. main.js seeds it from /api/energy and SSE refreshes
// it (`kind:"energy"`) whenever the agent spends, so it drops LIVE without anyone asking. ----
export const [energy, setEnergy] = createSignal({ cloud: false, known: false, balance: null, capacity: null });
// V2-785 — the account page the engine names (`account_url` in /api/config and /api/energy; "" on self-host), and
// the out-of-energy reason whose notice the person closed (a new exhaustion opens it again).
export const [accountUrl, setAccountUrl] = createSignal("");
export const [energyNoticeClosed, setEnergyNoticeClosed] = createSignal("");

// ---- system status (ⓘ panel: Hermes / voz / LLM / STT / TTS / cluster · credit + health) ----
export const [statusOpen, setStatusOpen] = createSignal(false);            // status panel visible?
export const [status, setStatus]         = createSignal({ overall: "unknown", items: [] });

// ---- the APPS WINDOW (V2-823): the launcher opened from the rail's corner — list on the left, a page per app ----
// Only whether it is open lives here; the list and the page are read when it opens (components/AppsWindow.js).
export const [appsWindowOpen, setAppsWindowOpen] = createSignal(false);

// ---- the LOCAL DAEMON (V2-575 P1: 🖥 icon + full-screen setup) ----
// Only whether the screen is OPEN lives here. Everything the screen shows comes from `services/daemon.js`,
// which owns the poll — the same split `update/watch.js` has, so the store never holds a stale copy of
// something the network already answered.
export const [daemonSetupOpen, setDaemonSetupOpen] = createSignal(false);
// The pairing card's last answer (null · `{code, expiresAt}` · `{loopback}` · `{unavailable}`), here so a redraw keeps it.
export const [daemonPair, setDaemonPair] = createSignal(null);

// ---- debug / observability side-column (resizable right column, fed by the SSE /events bus) ----
export const [debugOpen, setDebugOpen]   = createSignal(localStorage.getItem("hb_debug_open") === "1" || (typeof location !== "undefined" && new URLSearchParams(location.search).has("trace")));  // ?trace=<corr_id> deep link
export const [debugWidth, setDebugWidth] = createSignal(Math.max(300, parseInt(localStorage.getItem("hb_debug_w") || "460", 10)));

// ---- chat wall (text channel to the agent) ----
export const [chatOpen, setChatOpen]   = createSignal(false);  // chat wall panel visible?
// WHO is opening it (operator, 2026-10-04): from the LEFT BAR the wall nests to the left — a column, not a
// floating box; from the ORB it floats, unless the wall is already docked, in which case the docked shape is
// respected and it opens there. The shape is still the wall's own (hb_chat_dock / hb_chat_float); this is only
// the hint the opener leaves for the wall to read ONCE, on the open it belongs to. Nobody else reads it.
export const [chatOpenFrom, setChatOpenFrom] = createSignal(null);   // null | "bar" | "orb"
export function openChatFrom(from, tab) {
  if (tab) setChatTab(tab);
  setChatOpenFrom(from || null);
  setChatOpen(true);
}
// V2-728 — FOUR tabs, down from five: "chat" | "procesos" | "clusters" | "conectores". «Procesos» and
// «Crons» were the same object seen twice (a commission the brain is carrying out, and a commission with a
// clock on it), split across two tabs because they were built at different times and stored in different
// places.
//
// V2-744 — …and the tab is called PROCESOS again, id included, because the word «tarea» was reassigned by
// the operator: *«a las tareas que yo hago las llamo procesos (jobs en inglés) y las separo de las tareas
// personales del operador que van en su agenda»*. That is not a label change with an internal id left
// behind: `tareas` is the string a voice order carries («ábreme las tareas»), and while this door answered
// to it, that order opened the agent's own work instead of his shopping list. The id IS part of the
// routing, so it moved with the label.
//
// The OLD NAMES still arrive, from three directions that cannot be changed at once: the voice router
// (`nucleo/flash/panel_canon`), the action map, and the localStorage of every operator who left the wall on
// one of them. So this setter NORMALISES instead of the callers doing it — a rule each caller has to
// remember is a rule that ends up missing from one of them, which is a lesson already learned elsewhere.
// `crons` lands on «Procesos ▸ Periódicos», which is where it now lives. `tareas` is kept here, and ONLY
// here, for the rows an operator's own action map already stored: it is the same object he meant then.
const [chatTab, _setChatTab] = createSignal("chat");
export { chatTab };
const _TAB_ALIAS = { tareas: ["procesos", "live"], tasks: ["procesos", "live"], jobs: ["procesos", "live"],
                     workers: ["procesos", "live"], crons: ["procesos", "recurring"],
                     cron: ["procesos", "recurring"],
                     programadas: ["procesos", "scheduled"], scheduled: ["procesos", "scheduled"] };
// V2-761 — «Apps» (the widget catalogue) has two sub-tabs, Sistema and Custom, and the operator calls it
// «apps» or «widgets» indifferently; both words, and the custom sub-tab by name, land here.
const _APPS_ALIAS = { apps: "system", app: "system", widgets: "system", aplicaciones: "system",
                      "apps-custom": "custom", custom: "custom" };
const _TABS = ["chat", "procesos", "clusters", "red", "conectores", "apps"];   // red = the A2A Network (V2-866)
const [appsScope, setAppsScope] = createSignal("system");      // "system" | "custom"
export { appsScope, setAppsScope };
export const setChatTab = (tab) => {
  const raw = String(tab || "chat");
  const alias = _TAB_ALIAS[raw];
  if (alias) { setTaskScope(alias[1]); _setChatTab(alias[0]); return; }
  if (_APPS_ALIAS[raw]) { setAppsScope(_APPS_ALIAS[raw]); _setChatTab("apps"); return; }
  _setChatTab(_TABS.includes(raw) ? raw : "chat");
};
// The ENGINE's clock as this tab last read it (`noteServerTime`, from every event): the attention hold compares a
// verdict and a final on it (2026-11-17). The chat wall itself is a component of its own (behind its one bridge),
// written through `services/wall-bridge.js` — the store holds none of its lines.
let _skewMs = 0;
export const noteServerTime = (tMs) => { const t = Number(tMs); if (t > 0) _skewMs = t - Date.now(); };
export const serverNow = () => Date.now() + _skewMs;

// Convenience helpers used across services (mirror the old showAlert/hideAlert/setConn).
export const showAlert = (msg, onClick) => setAlert({ msg, onClick });
export const hideAlert = () => setAlert(null);
export const setConnState = (label, ok = false) => setConn({ label, ok });

// V2-792 — what happened on ANOTHER screen of the same agent: a card opened there, or one that plays on one screen
// at a time moved there. Each item is a passive chip `{key, id, dev, why, at}` (services/screens.js owns it).
export const [elsewhere, setElsewhere] = createSignal([]);

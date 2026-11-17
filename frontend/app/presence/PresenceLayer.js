// PresenceLayer.js — the agent's face in the BACKGROUND of the desk (V2-928): above the desk's backdrop, under every
// card, never catching a click. It exists only while presence is on — off means no canvas, no loop, no audio graph.
//
// What drives it, all read from what the screen already knows (nothing new is asked of the engine):
//   speaking  ← `store.botSpeaking` (the engine's own «this utterance reached the speaker») + the lip-sync model on the
//               agent's audio stream (`audio.onBotStream`, observe only — the page keeps playing it);
//   hearing   ← the person's real microphone level (`store.micLevel`) while the agent is quiet;
//   thinking  ← the person spoke and the agent has not answered yet (a short window, cleared by the agent's voice);
//   idle      ← the agent is stopped: the face rests, dimmed.
// The big eye (Orb.js) is HIDDEN, not deleted: the orb lives in the bottom bar (V2-623 dock) from now on.
import { h } from "../core/dom.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { onBotStream } from "../services/audio.js?v=2";
import { presenceOn, presenceFace, presenceCustom, syncPresence, DEFAULT_FACE } from "./state.js?v=1";
import { faceById } from "./catalog-api.js?v=1";
import { createFace } from "./face.js?v=1";

const HEAR = 0.05, THINK_S = 6;

/** The entry to wear: his choice, or the default when an id no longer exists. */
export const currentEntry = () => faceById(presenceFace(), presenceCustom()) || faceById(DEFAULT_FACE);

export function PresenceLayer() {
  syncPresence();
  let face = null, unsub = null, timer = 0, heardAt = 0, thinkUntil = 0;
  const host = h("div", { id: "presence", class: "hb-presence", "aria-hidden": "true" });
  const [tick, setTick] = createSignal(0);

  // The eye retires: the orb lives in the bar (a full-screen card already puts it there on its own).
  createEffect(() => { if (store.orbDock() !== "bar") store.setOrbDock("bar"); });

  createEffect(() => {
    const live = presenceOn();
    document.body.classList.toggle("hb-presence-on", live);
    if (live && !face) {
      face = createFace(host, { lipSync: true, entry: currentEntry(), className: "hb-presence-cv" });
      unsub = onBotStream((s) => (s ? face.observe(s) : face.detach()));
      const unlock = () => face && face.unlock();
      document.addEventListener("pointerdown", unlock, { once: true });
      timer = setInterval(() => setTick((n) => n + 1), 120);
    } else if (!live && face) {
      clearInterval(timer); if (unsub) unsub(); unsub = null;
      face.dispose(); face = null;
    }
  });
  createEffect(() => { const e = currentEntry(); if (face) face.setEntry(e); });

  // Mood from the screen's own signals, re-read a few times a second (the mic level moves faster than effects need).
  createEffect(() => {
    tick();
    if (!face) return;
    const now = performance.now() / 1000, speaking = store.botSpeaking(), state = store.agentState();
    const hearing = !speaking && store.micLevel() > HEAR;
    if (hearing) heardAt = heardAt || now; else if (heardAt) { if (now - heardAt > 0.6) thinkUntil = now + THINK_S; heardAt = 0; }
    if (speaking) thinkUntil = 0;
    const stopped = state === "off" || state === "stalled";
    const mood = stopped ? "idle" : now < thinkUntil ? "thinking" : "listening";
    face.setState({ mood, hearing, speaking });
    face.setAlpha(stopped ? 0.55 : 1);
  });
  return host;
}

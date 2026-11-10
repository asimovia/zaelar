// ============================================================================
// voice-arrival.js — the page is ready only when the AGENT is in the room (V2-873).
// A room is dispatched an agent when it is born, to the workers registered then. A page that asked for its room
// while the engine's worker was still registering got a room nobody ever joined, and after the boot overlay's
// safety timeout it showed a ready agent that was not there. Two doors close it:
//   · the token door answers 503 `voice_starting` until the worker is registered — the page waits and asks again;
//   · a room the agent has not joined within AGENT_WAIT_MS is left and asked for again — any cause (a dispatch that
//     never came, an entrypoint that died) ends in a new room, never in «ready».
// Both are bounded; past the bound the page says the agent is not available.
// ============================================================================
export const STARTING_TRIES = 40;        // × STARTING_EVERY_MS ≈ 2 min of a worker registering
export const STARTING_EVERY_MS = 3000;
export const AGENT_WAIT_MS = 25000;      // a dispatched agent joins in seconds; past this the room is empty
export const AGENT_TRIES = 3;

/** What a token answer is: "token" · "starting" (the worker is not registered yet) · "stopped" (any other refusal). */
export function tokenVerdict(res) {
  if (res && res.ok && res.token) return "token";
  if (res && res.error === "voice_starting") return "starting";
  return "stopped";
}

/** Is an agent among the room's remote participants? */
export function agentPresent(room) {
  try {
    for (const p of (room && room.remoteParticipants ? room.remoteParticipants.values() : [])) {
      if (p && (p.isAgent || String(p.identity || "").startsWith("agent-"))) return true;
    }
  } catch (_) {}
  return false;
}

/** A bounded retry: `arm(fn)` schedules fn once more and says whether the bound allowed it; `reset()` on success. */
export function boundedRetry(max, everyMs, setT = setTimeout, clearT = clearTimeout) {
  let n = 0, timer = null;
  return {
    arm(fn) {
      if (n >= max) return false;
      n += 1;
      if (timer) clearT(timer);
      timer = setT(() => { timer = null; fn(); }, everyMs);
      return true;
    },
    reset() { n = 0; if (timer) clearT(timer); timer = null; },
    get tries() { return n; },
  };
}

/** Watch a connected room: no agent within `ms` → `onMissing()`. Returns the cancel (call it when the agent joins). */
export function watchAgent(room, onMissing, ms = AGENT_WAIT_MS, setT = setTimeout, clearT = clearTimeout) {
  if (agentPresent(room)) return () => {};
  const timer = setT(() => { if (!agentPresent(room)) onMissing(); }, ms);
  return () => clearT(timer);
}

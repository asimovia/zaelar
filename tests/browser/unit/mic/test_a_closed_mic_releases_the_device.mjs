// ============================================================================
// test_a_closed_mic_releases_the_device.mjs — 2026-11-11.
//
// Closing the 🎤 only silenced the capture track (`enabled = false`): the browser kept the device open and its red
// recording dot lit. Closed now STOPS the tracks (the device is handed back) and opening asks for it again and adopts
// the fresh stream. Drives `frontend/app/services/mic-device.js` with fake streams.
//
// Run: node tests/browser/unit/mic/test_a_closed_mic_releases_the_device.mjs
// ============================================================================
import assert from "node:assert/strict";

const { createMicDevice } = await import("../../../../frontend/app/services/mic-device.js?v=1");

const fakeStream = () => {
  const tr = { readyState: "live", enabled: true, stop() { this.readyState = "ended"; } };
  return { tr, getAudioTracks: () => [tr], getTracks: () => [tr] };
};

// ── 1. close → the device is released; open → a fresh stream is acquired and adopted ─────────────────────────
{
  const first = fakeStream();
  let acquired = 0, adopted = null;
  const d = createMicDevice({ acquire: async () => { acquired++; return fakeStream(); }, adopt: async (s) => { adopted = s; } });
  assert.equal(d.release(first), true);
  assert.equal(first.tr.readyState, "ended",
               "THE BUG: a closed mic only disabled the track, and the browser kept the device (the red dot) captured");
  assert.equal(d.released(), true);
  assert.equal(d.release(first), false, "releasing twice is a no-op");
  assert.equal(await d.reacquire(), true);
  assert.equal(acquired, 1, "opening it asks the browser for the device again");
  assert.equal(adopted.tr.readyState, "live", "…and the session adopts the fresh capture");
  assert.equal(d.released(), false);
  assert.equal(await d.reacquire(), false, "nothing to reopen when it was never released");
}

// ── 2. closed again (or the session stopped) while the browser answered: the fresh stream is closed at once ──
{
  let adopted = 0, fresh = null;
  const d = createMicDevice({ acquire: async () => (fresh = fakeStream()), adopt: async () => { adopted++; } });
  d.release(fakeStream());
  assert.equal(await d.reacquire(() => true), false);
  assert.equal(adopted, 0);
  assert.equal(fresh.tr.readyState, "ended", "a stale reopen never leaves the device captured");
  assert.equal(d.released(), true, "…and the next open asks again");
}

// ── 3. a refused reopen is logged, never thrown; a chat-only silent stream holds no device ─────────────────────
{
  const logs = [];
  const d = createMicDevice({ acquire: async () => { throw Object.assign(new Error("no"), { name: "NotAllowedError" }); },
                              adopt: async () => {}, log: (w) => logs.push(w) });
  d.release(fakeStream());
  assert.equal(await d.reacquire(), false);
  assert.deepEqual(logs, ["released", "reopen_failed"]);
  const silent = Object.assign(fakeStream(), { __silent: true });
  assert.equal(createMicDevice({ acquire: async () => null, adopt: async () => {} }).release(silent), false);
}

// ── 4. two opens in a row share one request ────────────────────────────────────────────────────────────────────
{
  let n = 0;
  const d = createMicDevice({ acquire: async () => { n++; return fakeStream(); }, adopt: async () => {} });
  d.release(fakeStream());
  await Promise.all([d.reacquire(), d.reacquire()]);
  assert.equal(n, 1);
}

console.log("ok — a closed mic releases the device");

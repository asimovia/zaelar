# Speaker identity — knowing WHO is talking

**Mode: shadow measurement.** The speaker identifier labels every speech segment and logs the verdict; it
gates nothing, writes no memory and changes no prompt.
This document describes the MECHANISM. Deployment-specific policy is out of scope here.

## Why it exists

The mic is always open and the room is not the operator. Knowing who is speaking addresses three problems:

1. **Accidental identity writes.** A third party saying *"no, I'm not Ricard, I'm Joan"* reaches the same
   write path as the operator. The existing protection (`nucleo/memory_agent/gates.py::_plausibility_demote`)
   is a PLAUSIBILITY guard keyed on a value contradiction, not on who spoke — it holds when a name is already
   established, but by design it does not apply to an empty profile (the guard returns early — "no conflict in
   an empty profile") or to an explicit correction (`ingest.py`'s `_is_corr` bypasses it). A speaker label is
   the discriminator that covers those cases.
2. **Room speech carrying a command** could otherwise reach the canvas fast-paths.
3. **A TV is a human voice.** Energy gates and noise suppression cannot separate it — only a voiceprint can.

## Architecture: the BROWSER carries the cost

The fingerprint is computed **client-side**; only a tiny verdict (a label plus scores) crosses to the
backend, never the audio to analyze. When the backend and the browser run on different machines this keeps
the per-session CPU off the server; in a local run it is one machine and the split costs nothing either way.

```
mic ──► AnalyserNode (audio.js, already owned by the visualiser)
          └─► SpeakerID.tick()            ← rAF, browser
                ├─ energy Segmenter        (the LiveKit engine gives the client no VAD signal)
                ├─ frameFeatures()         pitch · spectral centroid · rms
                ├─ snapshot() per segment  median pitch, mean centroid/rms
                └─ classify() vs profiles  {operator, known:<id>, …}
                      └─► onUtterance ──► api.clientLog("🎙️ speaker", …) ──► observability
```

## Files

| File | Role |
|---|---|
| `frontend/app/lib/speaker-id.js` | Pure DSP core + the `SpeakerID` AnalyserNode adapter |
| `frontend/app/services/session-lk.js` | `_startSpeakerShadow()` / `_stopSpeakerShadow()`, the rAF, the log |
| `tests/browser/unit/voice/test_speaker_id_shadow.{mjs,py}` | Node **4.150**, 8 groups |

The pure half (`rmsOf`, `pitchOf`, `centroidOf`, `frameFeatures`, `snapshot`, `buildProfile`, `matchScore`,
`distancesTo`, `classify`, `Segmenter`) uses no browser globals, so it is driven directly from Node with
synthetic frames; the adapter is driven through a fake AnalyserNode. Nothing in the test needs a browser.

`frontend/app/lib/speaker-gate.js` is the predecessor from the legacy Pipecat path: still imported by the
legacy `session.js`, inactive on the LiveKit engine, where `session-lk.js::getGate()` returns `null`. It stays
in place because the legacy path still imports it.

## Multi-profile from the start

`classify(snapshot, profiles)` scores against a MAP, not a single profile. The operator is one entry;
household voices become entries under `known:<id>`, and an ONNX embedding (CAM++ via onnxruntime-web) can
replace `frameFeatures`/`matchScore` behind the same interface without the callers changing. That shape is
deliberate: it is what an embedding classifier needs anyway.

## Reading the shadow log

Rows arrive as observability `client` events labelled `🎙️ speaker`, one per speech segment:

| Field | Meaning |
|---|---|
| `label` | `enroll` · `operator` · `other` · `known:<id>` |
| `op_score` | the coarse VOTE against the operator's profile (0, ⅓, ⅔ or 1) |
| `d_mean`, `d_pitch`, `d_centroid` | **continuous** z-distances (0 = dead on the profile, 1 = one σ out) |
| `rms_ratio` | loudness vs the enrolled level (≪ 1 = far from the mic) |
| `pitch`, `centroid`, `rms` | the raw snapshot, for offline analysis |

Three more rows make *silence in the log* itself readable:

| Row | Says |
|---|---|
| `🎙️ speaker: armado` | the shadow started. **Its ABSENCE means the browser tab is running an older build** — the ES module is cached per page load, so a hard reload is required after any change here |
| `⚠️ speaker: no arrancó` | arming threw. It is logged explicitly rather than swallowed by a silent `catch`, so a module that failed to start is visible |
| `🎙️ speaker: nivel` | one-shot ~25 s in: the loudest frame seen vs the segmenter's start floor. If `peak_rms` < `start_floor`, no segment can ever open on that mic and the calibration — not the code — is what needs changing |

So: no `armado` row → stale tab. `armado` but no verdicts → check the `nivel` row.

**Use `d_mean`, not `op_score`, to choose a threshold.** `matchScore` is a three-criteria vote, so it can
only return a handful of discrete values. That is enough to classify and useless to threshold against; the
continuous distances are what a threshold should be chosen from.

## Two things that must never happen, and how they are prevented

- **The agent's own voice must never be enrolled as the operator.** TTS comes out of the speakers and back
  into the mic; echo cancellation attenuates it and does not remove it. `SpeakerID.suppressed()` (wired to
  `store.botSpeaking()`) discards anything in flight and fingerprints nothing while zaelar talks.
- **The shadow must never change behaviour.** It writes no memory, gates no turn, sends no data channel
  message, and touches no prompt. It is killable with `?nospk=1` or `localStorage.zaelar_spk_shadow=0`.

## Cost

`pitchOf` (autocorrelation over 70–400 Hz on a 2048-sample frame) runs in under a millisecond per frame;
throttled to every other rAF frame and only on speech, it uses a few percent of one core, and only while
somebody is talking. Silence costs an RMS pass. It runs on the main thread — within a 16 ms frame budget, and
an AudioWorklet is the escape hatch if an embedding model later makes this heavier.

## Design limits of single-track speaker identification

- **Continuous background speech** (a TV that never stops) means silence-based segment boundaries need not
  align with speaker changes.
- **One STT utterance can contain TWO speakers** — background speech and the operator's sentence can fuse
  into a single transcript. A per-utterance label cannot express that; overlapping speech is the hard case of
  any single-track approach.
- **The profile is per page load.** Each load re-enrolls, so a session's numbers are relative to that
  session's enrollment.
- **Auto-enrollment trusts whoever speaks first**, which is appropriate for shadow measurement.
- **Far-field and short utterances degrade any speaker verification**, which is why a hard voice-lock belongs
  behind an explicit opt-in, never a default.

## The interaction that matters for gating

`voice/attention.py::evaluate_content` short-circuits inside the active conversation window — *within the
window the turn is directed, full stop* (deliberate: it keeps the gate from going deaf mid-dialogue). So any
speaker check that is meant to gate must be consulted **before** that shortcut, or a perfect voiceprint would
still change nothing.

## Extension points

The design leaves room for: restricting writes to identity slots and `state` to the operator's voice, a
persisted known-voices file with a presence line, enrollment gated on directed turns or an explicit one-time
ceremony, and an opt-in voice-lock.

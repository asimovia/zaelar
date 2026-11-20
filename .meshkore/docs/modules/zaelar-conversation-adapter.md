# The pinned speech adapter, as the conversation ear needs it (V2-941 F0)

What the speech stack this engine pins (`livekit-agents==1.6.6`, `livekit-plugins-deepgram==1.6.6`, Deepgram Flux
`flux-general-multi`) actually delivers, measured, and what the ear of the conversation manager (`conversation/ear/`)
needs from it. This is the contract the F1 adapter is written against: every row says whether the fact is **exposed**
by the pinned plugin, **exposed raw** (Flux sends it, the plugin drops it), or **must be added**.

## How it was measured

- **Raw:** `tests/conversation/benchmarks/flux_probe.py <audio.wav> --out raw.jsonl` opens the Flux websocket with the
  ear's own settings (`voice/engine/core/config.py`: model, `eot_threshold` 0.7, `eager_eot_threshold` 0.5,
  `eot_timeout_ms` 1000), streams a 16 kHz mono PCM16 file in 20 ms frames at real time and records every message with
  its arrival time and how much audio had been sent. `--cut-at-s` stops the audio mid-sentence with no close message.
- **Through the plugin:** the same file through `livekit.plugins.deepgram.STTv2`, recording the `SpeechEvent`s.
- **Audio:** synthetic speech generated locally with a text-to-speech voice, one English and one Spanish file (11.4 s
  and 13.7 s), each with a 900 ms and a 700 ms pause in the middle of a sentence and a 2.5 s pause between two
  sentences; one extra English run cut at 4.5 s. **No human speech.** Rows marked *synthetic* are re-measured on
  human speech when labelled recordings exist (the 500-pause set of F0 part B).
- `--summarize` prints the figures below from the dumps without any transcript text. The dumps themselves are not kept
  in the repository.

## A1–A10

| # | Question | Measured | Status for the ear |
|---|---|---|---|
| A1 | Per-word or per-window times? | Every word of every `TurnInfo` carries `start` and `end` (873/873 words). The plugin keeps them: `SpeechData.words[i].start_time/end_time`, all non-zero (873/873). Each message also carries `audio_window_start/end`. | **Exposed.** `WordSpan.words[(text, t0_ms, t1_ms, conf)]` comes from the plugin's words. |
| A2 | Is there an «audio processed through» mark? | `audio_window_end` advances on every `TurnInfo` (106 of 108 consecutive pairs), **also in silence** (`Update` messages with zero words keep arriving), every ~240 ms (p50 239, p95 287 ms). | **Exposed raw / partly through the plugin.** The plugin forwards `audio_window_end` only on events that carry words (`_parse_transcription` returns nothing for an empty `words`), so the silent updates — the ones that prove the stream is alive — never reach the agent. `Watermark(processed_through_ms)` needs the adapter's own handler of `TurnInfo`. |
| A3 | Does the end-of-turn probability arrive? | `end_of_turn_confidence` and `turn_index` are present on **every** `TurnInfo` (110/110). | **Exposed raw, dropped by the plugin.** `EotHint.prob` and the per-turn index need the adapter's own handler (F1, in `voice/`). |
| A4 | Are words already given revised later? | Yes, inside a turn: 28 updates rewrote earlier words of the same turn (a word re-heard, a name re-cased, punctuation moved onto another word). Words of a turn that ended are not revised. | **The hypothesis of an open turn is revisable until its end.** `WordSpan.revision` = the update counter of the turn; the ear REPLACES a turn's words by `seq` (one `seq` per Flux turn), never appends (node 13.3). |
| A5 | Delay of the last word | A word is first seen p50 ~250 ms, p95 ~630–870 ms after its own `end`. `EagerEndOfTurn` arrived 311–673 ms after the last word; a confident `EndOfTurn` 461 ms after it; a timeout `EndOfTurn` (confidence 0.19–0.33) 1.56–1.71 s after it. *Synthetic.* | Sets `Config.close_cap_ms` ≤ 2500 with margin over the timeout path. Re-measure on human speech. |
| A6 | Stalled stream / lost packets | With the audio cut at 4.5 s and no close message, the last message arrived 159 ms after the last audio and then **nothing for 10 s**: no `EndOfTurn`, no `Update`. After a normal close message, the turn that was open got no `EndOfTurn` either. | A stall is **silent**: the ear detects it as the watermark not advancing while the wall clock does (`Config.stall_ms`), and the open intervention becomes `incomplete` — never closed, never actionable. |
| A7 | Playback acknowledgements | `PlaybackFinishedEvent.playback_position` is the duration the agent PUSHED (on an interruption, `voice/io.py`), not what a device played. | **Must be added in the client** (web and mobile): per-device `PlayoutAck(say_id, heard_chars)`; absent = unknown, never «heard». |
| A8 | Who opens turns? | The engine runs `AgentSession(turn_detection="stt")`: each `FINAL_TRANSCRIPT` starts a LiveKit turn. `livekit-agents` 1.6.6 has `turn_detection="manual"`, which ignores VAD-driven turns and leaves `commit_user_turn()` / `clear_user_turn()` to the caller. | **F1:** run the session with `turn_detection="manual"` so LiveKit is transport and the manager is the only one that opens a turn; the trace must show it. |
| A9 | A common clock | Word and window times are seconds of AUDIO from the stream start; the plugin adds `start_time_offset`. Arrival is wall clock. Over the 11–14 s runs arrival − window end stayed within p50 150 ms, p95 ~390 ms, with no trend. | The ear keeps both: audio time for word order and coverage, wall time for patience and stalls; the adapter maps audio time to wall time once per stream (`stream_t0_wall + audio_s`). Drift over 10 minutes is not measured yet. |
| A10 | Spanish | Spanish behaved like English: an eager hint at each mid-sentence pause (2), one resumed (`TurnResumed`), and the 900 ms pause in the English file was closed as a turn by a confident `EndOfTurn` (0.70 ≥ 0.7) before the sentence went on. *Synthetic.* | Confirms the class the ear exists for: a provider's end of turn is a HINT; a closed intervention can still be reopened (or amended after its seal) when he goes on. |

## What the ear needs that the pinned plugin does not give

Built (B8a): `voice/engine/pipeline/ear_feed.py` turns each provider message into the ear's facts on one wall clock
(item 1 below); the facts cross to the body on a lossless lane of the
body link (`send_ear`: numbered, carried until answered, a hole declared as a `gap` past its ceiling); the body applies
each once (`nucleo/conversation_host/ear_in.py`) and a hole ends what the ear was hearing incomplete (`link_gap`).

Built (B8b): items 1 and 3, and the playback of the voice process itself. Before it builds a session the voice process
asks the body's switch (`/api/voice/child/conv`, the room's own `conv` flag first, `voice_session.ask`). It builds the
manager's session only on yes AND with the provider's turns, and what it built rides «session started» as the
session's decision on the body (`voice_session.started`). In that session (`voice/engine/pipeline/ear_tap.py`):
- every raw provider message reaches `ear_feed` first and the plugin's own handler runs untouched after it; each
  stream has its own clock;
- after an end of turn the session's own turn is cleared, never committed;
- the ear's own edges of his voice come from the VAD's frames with a 200 ms quiet tail (E1), `echo_safe` false while
  our voice sounds, and our playback comes from the agent's state;
- turn detection is `manual`, with no early reply and no greeting (the body's kickoff answers none);
- an `llm_node` LiveKit opens anyway is counted (`livekit_turns`), said as an alert, and answered with an empty turn;
- the owed lines are claimed for the voice while it lives.

At the job's end the warm STT is given back untapped. Not wired yet: the app writing the session's `conv` flag into
the room's metadata (the account's key and the environment decide meanwhile), and the clients' playback (item 2).


1. A `TurnInfo` handler of its own (F1, in `voice/`, next to `voice/engine/speech/stt/deepgram.py`), forwarding for
   every message: event, `turn_index`, `end_of_turn_confidence`, `audio_window_end` (also with no words) and the words
   with their times. The plugin's `SpeechEvent`s lose the probability, the turn index and the silent watermark.
2. Per-device playback acknowledgements from the clients.
3. `turn_detection="manual"` on the session, so only the manager opens a turn.
4. Signal times on the manager's wall clock (`Clock.now_ms`, mapped once per stream as in A9): the manager's sweep
   ticks the ear with that clock, so an intervention no signal ever ends (a dropped phone) still ends within its cap or
   its stall, and a reopen is given back past `cross_channel_hold_ms` even while the ear hears it.

## Not verified

Human speech (A5 and A10 are synthetic), noise, Bluetooth and mobile capture, packet loss on a real network (A6 was a
clean cut), clock drift over long sessions (A9), and the client SDKs' playback position (A7).

# audio3a — five audio scenarios against the real Flux, as token fixtures

Synthetic voices mixed into realistic streams (`tests/conversation/benchmarks/audio/`), streamed through Deepgram
Flux at real time with the engine ear's configuration, and exported here with every word replaced by a token
(`export_fixtures.py`). No audio and no words: a level-1 test replays them through the conversation package.

## Files

- `<scenario>.jsonl` — one ear signal per line, **in arrival order**, in the shapes of `conversation/ear/signals.py`:
  - `WordSpan` — one per Flux `TurnInfo` that carries words: `seq` = Flux `turn_index`, `revision` = the n-th message
    of that turn, `final` only on its `EndOfTurn`, `window` = the audio window, words `[token, t0_ms, t1_ms, conf]`;
  - `EotHint` — `EagerEndOfTurn` / `TurnResumed` / `EndOfTurn`, with Flux's `end_of_turn_confidence` as `prob`;
  - `Watermark` — every `TurnInfo`'s `audio_window_end` (Flux beats in silence too: no synthetic beats are needed);
  - `VadEdge` — the engine's Silero read per window with the adapter's quiet tail (v3.1 §1.6 bis, E1:
    `quiet_ms` 200, on 0.5, off 0.35): `t_ms` is where the voice rose or fell, `arrived_ms` when the edge is known.

  Every line has `arrived_ms` (when it would reach the ear live). Feed the lines in file order; do not re-sort them
  and do not add the replay's synthetic watermark beats. `t_ms` is the signal's own time where the ear reads one
  (`VadEdge`, `EotHint`) and the arrival elsewhere.
- `labels.json` — per scenario:
  - `segments` — who spoke when, by ROLE only (`user`, `other` = a second person, `tv`, `cough`), with
    `start_ms`/`end_ms`, the user `turn` it belongs to, whether it was `cut` off, and its words as tokens with times
    where the voice gave them (the same token for the same word as in the signals);
  - `turns` — the person's turns (thoughts): the segments that form each, and `end_ms`, the instant the person truly
    finished; `kind` is `complete` or `cut_off`;
  - `provider_turns` — Flux's own turns: when its end arrived, its confidence, token count, first and last word;
  - `measured` — what the manager did on this stream at `measured_on` (the batch it handed the model: units, false
    cuts, lines said while a turn was still going, turns left open while the audio ran, waits, exposure of the
    stranger segments, runs started/held/superseded).

All times are ms from the start of the stream, which is the audio clock and the wall clock of the run at once.
Arrival minus audio time is Flux's own lag (adapter doc A5, A9).

## The scenarios

| Scenario | What it stresses |
|---|---|
| `es-nvidia-pauses` | one thought in three pieces with 0.9 s and 1.4 s pauses, then a short follow-up turn |
| `en-crosstalk-in-pause` | a second person speaks inside the person's pause (gaps of 350 and 250 ms) |
| `es-cut-off-and-correction` | a self-correction inside a turn; then the person is cut off by someone talking over |
| `en-tv-and-cough` | continuous TV speech in the background; a cough inside a pause |
| `mixed-es-en-switch` | the person switches language inside one thought after a 0.7 s pause |

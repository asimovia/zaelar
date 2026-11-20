"""A raw Flux dump (`flux_probe.raw`) and the engine's own VAD → the conversation ear's signals, on ONE clock.

The probe streams the scenario in real time from audio 0, so «ms since the first frame» is both the scenario's
timeline and the wall clock of the run: word times (`start`/`end` × 1000) and window ends are audio ms, arrival is
wall ms, and the two differ only by Flux's lag — the mapping the adapter does once per stream (adapter doc A9).

Each `TurnInfo` becomes, as the speech adapter will build them (adapter doc A1–A4):
  · words, if any → `WordSpan(seq=turn_index, revision=n-th message of that turn, final=False)`;
  · `EndOfTurn` → the same words `final=True`, then `EotHint(end, prob, terminal)` — terminal when its last word
    ends a sentence (`TERMINAL_MARKS`);
  · `EagerEndOfTurn` / `TurnResumed` → `EotHint(eager|resumed, prob)`;
  · every message → `Watermark(audio_window_end)`.
The VAD is the engine's Silero (`voice/engine/speech/vad/silero.py`), offline over the same audio, read per window
the way the speech adapter reads it (v3.1 §1.6 bis, E1): a RISE at the first window at or above the activation
threshold, a FALL once the probability stays under the deactivation threshold for `VAD_QUIET_MS` — the fall is
dated where the quiet began and arrives `VAD_QUIET_MS` later. (`edges="eos"` keeps the plugin's own end of speech,
for comparison.)

Every signal carries `arrived_ms` (when it would reach the ear live) and the list is in arrival order: feed it in that
order. `t_ms` is the signal's own time where the ear reads one (`VadEdge`, `EotHint`) and the arrival elsewhere, so a
replay that orders by `t_ms` stays close.
"""
from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

#: The sentence ends Flux writes (it punctuates its transcript): an end of turn closed on one of these is TERMINAL
#: (v3.1 §1.6 ter); one closed on a comma, a function word or nothing is not. None when the turn had no word.
TERMINAL_MARKS = (".", "?", "!", "…")
VAD_QUIET_MS = 200            # E1: the adapter's own short tail
VAD_ON, VAD_OFF = 0.5, 0.35   # the engine's activation threshold, and the plugin's deactivation (activation − 0.15)
RISE_LAG_MS = 32              # a rise is known when its window is inferred


def load_raw(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _vad_events(wav: Path) -> list:
    import numpy as np
    from livekit import rtc
    from voice.engine.speech.vad.silero import build
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    stream = build().stream()
    per = rate // 50                                          # 20 ms frames, as the engine pushes them
    samples = np.frombuffer(pcm, dtype="<i2")
    events: list = []

    async def push() -> None:
        for i in range(0, len(samples), per):
            chunk = samples[i: i + per]
            stream.push_frame(rtc.AudioFrame(chunk.tobytes(), rate, 1, len(chunk)))
            if i % (per * 25) == 0:
                await asyncio.sleep(0)
        stream.end_input()

    pusher = asyncio.create_task(push())
    async for ev in stream:
        events.append(ev)
    await pusher
    return events


def vad_edges(wav: Path, mode: str = "e1") -> list[tuple[str, int, int]]:
    """`[(edge, t_ms, arrived_ms)]`. `e1`: per-window probability with the adapter's quiet tail (§1.6 bis E1);
    `eos`: the plugin's own start/end of speech."""
    from livekit.agents import vad as agents_vad
    events = asyncio.run(_vad_events(wav))
    edges: list[tuple[str, int, int]] = []
    if mode == "eos":
        for ev in events:
            if ev.type == agents_vad.VADEventType.START_OF_SPEECH:
                t = int(round((ev.timestamp - ev.speech_duration) * 1000))
                edges.append(("rise", t, t + RISE_LAG_MS))
            elif ev.type == agents_vad.VADEventType.END_OF_SPEECH:
                t = int(round((ev.timestamp - ev.silence_duration) * 1000))
                edges.append(("fall", t, int(round(ev.timestamp * 1000))))
        return edges
    up, quiet_from = False, None
    for ev in events:
        if ev.type != agents_vad.VADEventType.INFERENCE_DONE:
            continue
        t = int(round(ev.timestamp * 1000))                    # end of the inferred window
        p = float(ev.probability)
        if not up and p >= VAD_ON:
            up, quiet_from = True, None
            edges.append(("rise", t - RISE_LAG_MS, t))
        elif up:
            if p < VAD_OFF:
                quiet_from = quiet_from if quiet_from is not None else t - RISE_LAG_MS
                if t - quiet_from >= VAD_QUIET_MS:
                    up = False
                    edges.append(("fall", quiet_from, t))
                    quiet_from = None
            else:
                quiet_from = None
    return edges


def signals(raw: list[dict], edges: list[tuple[str, int, int]], stream: str = "d1",
            playback: list[tuple[int, int]] = ()) -> list[dict]:
    """`playback`: the windows in which OUR voice was playing on this device (the engine knows them); a rise inside
    one is not echo-safe, as the adapter will mark it."""
    out: list[dict] = []
    rev: dict[int, int] = {}
    for m in raw:
        x, t = m["msg"], int(round(m["arrived_ms"]))
        if x.get("type") != "TurnInfo":
            continue
        seq = int(x.get("turn_index") or 0)
        a, b = int(round(1000 * float(x.get("audio_window_start") or 0))), int(round(1000 * float(x.get("audio_window_end") or 0)))
        words = [[w.get("word", ""), int(round(1000 * w["start"])), int(round(1000 * w["end"])),
                  float(w.get("confidence", 1.0))] for w in (x.get("words") or [])]
        ev = x.get("event")
        prob = x.get("end_of_turn_confidence")
        if words:
            rev[seq] = rev.get(seq, 0) + 1
            out.append({"sig": "WordSpan", "stream": stream, "seq": seq, "revision": rev[seq],
                        "final": ev == "EndOfTurn", "words": words, "window": [a, b], "t_ms": t, "arrived_ms": t})
        if ev == "EndOfTurn":
            last = str((x.get("words") or [{}])[-1].get("word") or "") if x.get("words") else ""
            out.append({"sig": "EotHint", "stream": stream, "source": "flux", "kind": "end", "prob": prob, "t_ms": t,
                        "arrived_ms": t, "terminal": last.rstrip().endswith(TERMINAL_MARKS) if last else None})
        elif ev == "EagerEndOfTurn":
            out.append({"sig": "EotHint", "stream": stream, "source": "flux", "kind": "eager", "prob": prob, "t_ms": t,
                        "arrived_ms": t})
        elif ev == "TurnResumed":
            out.append({"sig": "EotHint", "stream": stream, "source": "flux", "kind": "resumed", "prob": prob,
                        "t_ms": t, "arrived_ms": t})
        out.append({"sig": "Watermark", "stream": stream, "processed_through_ms": b, "t_ms": t, "arrived_ms": t})
    for edge, t, arrived in edges:
        sig = {"sig": "VadEdge", "endpoint": stream, "edge": edge, "t_ms": t, "arrived_ms": arrived}
        if edge == "rise" and any(a <= t <= b for a, b in playback):
            sig["echo_safe"] = False
        out.append(sig)
    return sorted(out, key=lambda s: s["arrived_ms"])    # stable: a final keeps its place before its EotHint


def flux_turns(raw: list[dict]) -> list[dict]:
    """Flux's own turns, as the old path takes them (`turn_detection="stt"`: each EndOfTurn is a LiveKit turn): the
    words of the turn's last message and when its end arrived."""
    turns: dict[int, dict] = {}
    for m in raw:
        x = m["msg"]
        if x.get("type") != "TurnInfo":
            continue
        seq = int(x.get("turn_index") or 0)
        d = turns.setdefault(seq, {"seq": seq, "words": [], "end_ms": None, "eot_prob": None})
        if x.get("words"):
            d["words"] = [[w.get("word", ""), int(round(1000 * w["start"])), int(round(1000 * w["end"]))]
                          for w in x["words"]]
        if x.get("event") == "EndOfTurn" and d["end_ms"] is None:
            d["end_ms"], d["eot_prob"] = int(round(m["arrived_ms"])), x.get("end_of_turn_confidence")
    return [turns[k] for k in sorted(turns)]

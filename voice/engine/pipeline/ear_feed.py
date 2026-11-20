"""ear_feed.py — what the voice process hears, as facts for the conversation manager's ear (V2-941, B8).

A fixed translation, no judgement (the adapter doc, A1–A10): each message of the speech provider becomes the facts the
ear reads, on ONE wall clock. Audio times (seconds since the stream started) are mapped once per stream to wall
milliseconds (`StreamClock`, A9); the arrival time travels apart, for telemetry.

  StartOfTurn / Update / TurnResumed with words → `words`  (the turn's index is its `seq`; its update count the
                                                            `revision`: the provider rewrites an open turn's words, A4)
  EndOfTurn                                     → `words` final + `eot` end, with the provider's confidence
  EagerEndOfTurn                                → `eot` eager       TurnResumed → `eot` resumed
  every message                                 → `mark` (audio processed through: the watermark, A2 — also in silence)

The provider's end-of-turn confidence is carried on every `eot` fact as it came (`prob`): the ear decides nothing with
it, and it is logged so it can be measured. A fact is a plain dict (`{"t": kind, …}`): it travels on the body link.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

#: the provider's event names (Deepgram Flux `TurnInfo.event`)
START, UPDATE, RESUMED, EAGER, END = "StartOfTurn", "Update", "TurnResumed", "EagerEndOfTurn", "EndOfTurn"


@dataclass
class StreamClock:
    """Audio seconds of one stream → wall milliseconds, fixed at the stream's first message (A9)."""
    t0_wall_ms: int | None = None

    def wall(self, audio_s: float, now_ms: int | None = None) -> int:
        if self.t0_wall_ms is None:
            now = int(time.time() * 1000) if now_ms is None else now_ms
            self.t0_wall_ms = now - int(round(float(audio_s) * 1000))
        return self.t0_wall_ms + int(round(float(audio_s) * 1000))


@dataclass
class Turns:
    """Per stream: the update count of each provider turn (its `revision`)."""
    revisions: dict = field(default_factory=dict)

    def next(self, turn: int) -> int:
        self.revisions[turn] = self.revisions.get(turn, 0) + 1
        return self.revisions[turn]


def from_turninfo(msg: dict, *, stream: str, clock: StreamClock, turns: Turns, now_ms: int | None = None,
                  terminal: bool | None = None) -> list[dict]:
    """One provider message → the ear's facts. `terminal`: whether the provider closed its transcript with a sentence
    end (the language pack's marks decide it, outside this function); None when unknown."""
    event = str(msg.get("event") or "")
    turn = int(msg.get("turn_index") or 0)
    end_s = float(msg.get("audio_window_end") or 0.0)
    start_s = float(msg.get("audio_window_start") or 0.0)
    arrived = int(time.time() * 1000) if now_ms is None else now_ms
    through = clock.wall(end_s, arrived)
    words = [(str(w.get("word") or ""), clock.wall(float(w.get("start") or 0.0), arrived),
              clock.wall(float(w.get("end") or 0.0), arrived), float(w.get("confidence") or 1.0))
             for w in msg.get("words") or () if str(w.get("word") or "")]
    prob = msg.get("end_of_turn_confidence")
    prob = float(prob) if isinstance(prob, (int, float)) else None
    out: list[dict] = []
    if words and event in (START, UPDATE, RESUMED, END, EAGER):
        out.append({"t": "words", "stream": stream, "turn": turn, "rev": turns.next(turn), "final": event == END,
                    "words": [list(w) for w in words], "window": [clock.wall(start_s, arrived), through],
                    "arrived": arrived})
    if event == END:
        out.append({"t": "eot", "stream": stream, "kind": "end", "prob": prob, "t_ms": through, "terminal": terminal,
                    "arrived": arrived})
    elif event == EAGER:
        out.append({"t": "eot", "stream": stream, "kind": "eager", "prob": prob, "t_ms": through, "arrived": arrived})
    elif event == RESUMED:
        out.append({"t": "eot", "stream": stream, "kind": "resumed", "prob": prob, "t_ms": through, "arrived": arrived})
    out.append({"t": "mark", "stream": stream, "through": through, "arrived": arrived})
    return out


def vad(endpoint: str, edge: str, t_ms: int, *, echo_safe: bool = True) -> dict:
    """A rise or a fall of the voice on this device (`edge`), at `t_ms` on the wall clock."""
    return {"t": "vad", "stream": endpoint, "edge": edge, "t_ms": int(t_ms), "echo_safe": bool(echo_safe)}


def playback(endpoint: str, speaking: bool, t_ms: int) -> dict:
    """Our own voice started or stopped sounding on this device."""
    return {"t": "playback", "stream": endpoint, "speaking": bool(speaking), "t_ms": int(t_ms)}

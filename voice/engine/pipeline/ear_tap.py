"""ear_tap.py — what the voice process hears, handed to the conversation manager's ear (V2-941, v3.1 §1.7).

Installed ONLY in a session of the manager (`child_session.py`, `manual`); in every other session nothing here runs.

  · the provider's tap (`install_stt`): every raw Flux message goes to `ear_feed` BEFORE the plugin's own handler, which
    runs untouched afterwards — what the plugin emits does not change. Each fact goes on the body link's lossless lane
    (`body_link.send_ear`). `terminal`: the transcript the provider closed a turn with ends with its punctuation of a
    sentence end (Flux writes it; these are its marks, not words of any language);
  · the ear's own edges of his voice (`VadEdges`, E1): rises and falls from the VAD's frames with a short quiet tail
    (`vad_quiet_ms`, 200 ms), not the VAD's end of speech, which comes later: a 250–350 ms gap between two voices is
    already a fall and a rise. `echo_safe` is false while our own voice sounds;
  · our playback (`playback`): our voice started or stopped sounding.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from voice.engine.pipeline import ear_feed

logger = logging.getLogger("zaelar.voice.ear_tap")

#: the provider's punctuation of a sentence end
TERMINAL_MARKS = (".", "?", "!", "…", "。", "？", "！")
VAD_QUIET_MS = 200
#: the device this process hears for: the holder of the session (`nucleo/conversation_host/voice_session.ENDPOINT`)
ENDPOINT = "holder"


def _now_ms() -> int:
    return int(time.time() * 1000)


def terminal_of(msg: dict) -> bool | None:
    text = str(msg.get("transcript") or " ".join(str(w.get("word") or "") for w in msg.get("words") or ())).rstrip()
    return text.endswith(TERMINAL_MARKS) if text else None


class Tap:
    """One stream of one device: its clock, its turns, and where the facts go."""

    def __init__(self, endpoint: str, send: Callable[[dict], None]) -> None:
        self.endpoint, self.send = endpoint, send
        self.clock, self.turns = ear_feed.StreamClock(), ear_feed.Turns()
        self.speaking = False                          # our own voice sounds (playback)
        self.edges = VadEdges(self)
        self.on_end: Callable[[], None] | None = None
        self.on_barge: Callable[[], object] | None = None   # cut our voice (the local rule)
        self.min_barge_ms = 500
        self.playing_since: int | None = None

    def new_stream(self) -> None:
        self.clock, self.turns = ear_feed.StreamClock(), ear_feed.Turns()

    def on_message(self, msg: dict) -> None:
        if not isinstance(msg, dict) or msg.get("type") != "TurnInfo":
            return
        end = msg.get("event") == ear_feed.END
        for fact in ear_feed.from_turninfo(msg, stream=self.endpoint, clock=self.clock, turns=self.turns,
                                           terminal=terminal_of(msg) if end else None):
            self.send(fact)

    def playback(self, speaking: bool, now_ms: int | None = None) -> None:
        if speaking != self.speaking:
            now = _now_ms() if now_ms is None else now_ms
            self.speaking, self.playing_since = speaking, (now if speaking else None)
            self.send(ear_feed.playback(self.endpoint, speaking, now))


class VadEdges:
    """E1: a rise at the first speaking frame after quiet; a fall once `VAD_QUIET_MS` passed with no speaking frame,
    stamped at the last speaking frame.

    The LOCAL CUT RULE (v3.1 §1.7, E7) lives here too: LiveKit interrupts nothing in a manual session, so while our
    voice sounds, his voice that ROSE after our line began and has lasted `min_barge_ms` cuts it — once per rise. A
    voice that was already up when our line began (a television) never cuts it, and a cough under the threshold does
    nothing."""

    def __init__(self, tap: Tap) -> None:
        self.tap, self.up, self.last_speech = tap, False, 0
        self.rose_at, self.cut = 0, False

    def frame(self, speaking: bool, now_ms: int | None = None) -> None:
        now = _now_ms() if now_ms is None else now_ms
        if speaking:
            if not self.up:
                self.up, self.rose_at, self.cut = True, now, False
                self.tap.send(ear_feed.vad(self.tap.endpoint, "rise", now, echo_safe=not self.tap.speaking))
            self.last_speech = now
            self._barge(now)
        elif self.up and now - self.last_speech >= VAD_QUIET_MS:
            self.up = False
            self.tap.send(ear_feed.vad(self.tap.endpoint, "fall", self.last_speech, echo_safe=not self.tap.speaking))

    def _barge(self, now: int) -> None:
        if _barge_due(self, now):
            self.cut = True
            try:
                self.tap.on_barge()
            except Exception as e:  # noqa: BLE001 — a cut that fails never stops the ear
                logger.warning(f"ear tap: our voice was not cut ({e!r})")


def _barge_due(edges: "VadEdges", now: int) -> bool:
    tap = edges.tap
    return (tap.speaking and tap.on_barge is not None and not edges.cut and tap.playing_since is not None
            and edges.rose_at >= tap.playing_since and now - edges.rose_at >= tap.min_barge_ms)


def install_stt(stt, tap: Tap):
    """Every stream this STT opens hands its raw messages to `tap` first, then to the plugin as before; after an end of
    turn the session's own turn is cleared (`tap.on_end`: nothing of LiveKit's accumulates). Each stream has its own
    clock and turns. The STT may be the process's warm one, shared by the next session: `uninstall` gives it back."""
    uninstall(stt)
    open_stream = stt.stream

    def stream(*a, **kw):
        s = open_stream(*a, **kw)
        original = s._process_stream_event
        tap.new_stream()

        def process(data):
            try:
                tap.on_message(data)
            except Exception as e:  # noqa: BLE001 — the ear's report never breaks the plugin's own path
                logger.warning(f"ear tap: a message was not handed over ({e!r})")
            out = original(data)
            if isinstance(data, dict) and data.get("event") == ear_feed.END and tap.on_end is not None:
                tap.on_end()
            return out

        s._process_stream_event = process
        return s

    stt.stream = stream
    stt._zaelar_ear_stream = open_stream
    return stt


def uninstall(stt) -> None:
    open_stream = getattr(stt, "_zaelar_ear_stream", None)
    if open_stream is not None:
        stt.stream = open_stream
        del stt._zaelar_ear_stream


def manual(turn_handling: dict) -> dict:
    """A session of the manager: LiveKit opens no turn of its own (no end of turn, no early reply). What he said goes
    to the manager's ear; the session's own turn is only ever cleared, never committed."""
    return {**turn_handling, "turn_detection": "manual", "preemptive_generation": {"enabled": False}}


def flag_of(metadata: str):
    """The session's own `conv` flag, if the room carries one in its metadata (JSON); None when it says nothing."""
    import json
    try:
        got = json.loads(metadata) if metadata else {}
    except ValueError as e:
        logger.warning(f"ear tap: the room's metadata is not JSON, no flag read ({e!r})")
        return None
    return got.get("conv") if isinstance(got, dict) else None


def tap_vad(inner, tap: Tap):
    """The session's VAD, its frames also read by the ear's own edges (E1). Delegates everything to `inner`."""
    from livekit.agents import vad as vadmod

    class _Stream:
        def __init__(self, s):
            self._s = s

        def push_frame(self, frame):
            return self._s.push_frame(frame)

        def end_input(self):
            return self._s.end_input()

        def flush(self):
            return self._s.flush()

        async def aclose(self):
            return await self._s.aclose()

        def __aiter__(self):
            return self

        async def __anext__(self):
            ev = await self._s.__anext__()
            if ev.type == vadmod.VADEventType.INFERENCE_DONE:
                try:
                    tap.edges.frame(bool(ev.speaking))
                except Exception as e:  # noqa: BLE001 — the ear's report never breaks the session's VAD
                    logger.warning(f"ear tap: a VAD frame was not read ({e!r})")
            return ev

    class _VAD(vadmod.VAD):
        def __init__(self):
            super().__init__(capabilities=inner.capabilities)

        def stream(self):
            return _Stream(inner.stream())

    return _VAD()

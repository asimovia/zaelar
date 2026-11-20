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

import itertools
import logging
import time
from typing import Callable

from voice.engine.pipeline import ear_feed

logger = logging.getLogger("zaelar.voice.ear_tap")

#: the provider's punctuation of a sentence end
TERMINAL_MARKS = (".", "?", "!", "…", "。", "？", "！")
VAD_QUIET_MS = 200
#: the stand-in's turns are numbered apart from the provider's own (`turn_index`), never mistaken for one of them
STAND_IN_TURNS = 1_000_000
#: his voice up and no message of the provider for this long: it stalled, and what it was hearing is lost
PROVIDER_STALL_MS = 2000
#: a rise this close to our line's start is how our own voice comes back with no echo cancellation: a barge-in that
#: cuts is never sent again as his voice inside it (it would open an intervention of our own echo)
ECHO_ONSET_MS = 400
#: how long a test plays a rise over our line: past `min_barge_ms`, never cut without words
WORDLESS_BARGE_MS = 700
#: the device this process hears for: the holder of the session (`nucleo/conversation_host/voice_session.ENDPOINT`)
ENDPOINT = "holder"
#: the epochs of this PROCESS, one per stream of any session: a second session's first stream never reuses the first's
_EPOCHS = itertools.count(1)


def _now_ms() -> int:
    return int(time.time() * 1000)


def terminal_of(msg: dict) -> bool | None:
    text = str(msg.get("transcript") or " ".join(str(w.get("word") or "") for w in msg.get("words") or ())).rstrip()
    return text.endswith(TERMINAL_MARKS) if text else None


class Tap:
    """One stream of one device: its clock, its turns, and where the facts go."""

    def __init__(self, endpoint: str, send: Callable[[dict], None]) -> None:
        self.endpoint, self._out = endpoint, send
        self.epoch = 0                                 # one per stream: Flux numbers its turns from 0 in each one
        self.clock, self.turns = ear_feed.StreamClock(), ear_feed.Turns()
        self.speaking = False                          # our own voice sounds (playback)
        self.edges = VadEdges(self)
        self.on_end: Callable[[], None] | None = None
        self.fallback, self.stand_in_turns = False, 0       # the titular fell: the stand-in's finals are the words
        self.titular_up = True
        self.seen, self.last_turn, self.last_end = 0, 0, 0.0
        self.last_msg_ms, self.stall_said = 0, False
        self.on_barge: Callable[[], object] | None = None   # cut our voice (the local rule)
        self.min_barge_ms = 500
        self.playing_since: int | None = None
        self.line = ""                                 # the text of our line now sounding (`/voice/say`)
        self.heard: tuple[str, ...] = ()               # the words of his turn in course, as the provider has them

    def provider_quiet(self, now: int) -> None:
        """His voice is up and the provider has answered nothing for `PROVIDER_STALL_MS`: what the ear is hearing is
        being lost — a gap, once until the provider speaks again (the voice process knows the audio flows; the body
        cannot tell a stalled provider from an idle stream)."""
        if self.seen and not self.stall_said and not self.fallback and now - self.last_msg_ms >= PROVIDER_STALL_MS:
            self.stall_said = True
            logger.warning("ear tap: his voice is up and the provider has gone quiet: a gap")
            self.send({"t": "gap", "streams": [self.endpoint], "t_ms": now})

    def send(self, fact: dict) -> None:
        self._out({**fact, "epoch": self.epoch})

    def _reconnected(self, msg: dict) -> bool:
        """A reconnect of the provider's websocket inside one stream: it says `Connected` again, or its turn number or
        its audio clock goes backwards — what came after is a new stream for the ear (a new epoch, a new clock, a gap)."""
        if not self.seen:
            return False
        if msg.get("type") == "Connected":
            return True
        return msg.get("type") == "TurnInfo" and (int(msg.get("turn_index") or 0) < self.last_turn
                                                  or float(msg.get("audio_window_end") or 0.0) < self.last_end - 0.5)

    def new_stream(self) -> None:
        """A stream begins: its own clock, its own turns and its own epoch. The one before it ended: if it was hearing a
        turn of his not yet ended, that ends incomplete — a declared gap, never words lost under a turn number used
        again. A stream that ended clean (its last turn closed, or none begun) leaves nothing to declare."""
        self.clock, self.turns = ear_feed.StreamClock(), ear_feed.Turns()
        if self.epoch and self.heard:
            self.send({"t": "gap", "streams": [self.endpoint], "t_ms": _now_ms()})
        self.heard = ()
        self.epoch = next(_EPOCHS)
        self.seen, self.last_turn, self.last_end = 0, 0, 0.0

    def titular_available(self, available: bool) -> None:
        """The titular provider fell, or is up again. Falling, what the ear was hearing ends incomplete — declared,
        never silent — and the stand-in is the MAIN stream: its finals are the ear's words. Up again, the stand-in STAYS
        the main stream (the adapter never moves a running one): its finals are still read, until a stream of the
        titular opens with the titular up — that one is the new main (`titular_opened`)."""
        self.titular_up = available
        if not available and not self.fallback:
            self.fallback = True
            logger.warning("ear tap: the titular STT fell; the stand-in's finals are the ear's words until it is main")
            self.send({"t": "gap", "streams": [self.endpoint], "t_ms": _now_ms()})

    def titular_opened(self) -> bool:
        """A stream of the titular opens. With the titular down it is the adapter's RECOVERY stream, fed the same audio:
        never heard (False). Up, it is the main stream — a new epoch, and the stand-in is read no more."""
        if not self.titular_up:
            return False
        self.fallback = False
        self.new_stream()
        return True

    def final_transcript(self, text: str, now_ms: int | None = None) -> None:
        """A final of the STAND-IN (no turns of its own): one closed turn — its words, its end, the watermark."""
        if not self.fallback or not str(text or "").strip():
            return
        now = _now_ms() if now_ms is None else now_ms
        self.stand_in_turns += 1
        turn, t = STAND_IN_TURNS + self.stand_in_turns, now
        words = [[w, t, t, 1.0] for w in str(text).split()]
        self.send({"t": "words", "stream": self.endpoint, "turn": turn, "rev": 1, "final": True, "words": words,
                   "window": [t, t], "arrived": now})
        self.send({"t": "eot", "stream": self.endpoint, "kind": "end", "prob": None, "t_ms": t,
                   "terminal": str(text).rstrip().endswith(TERMINAL_MARKS), "arrived": now})
        self.send({"t": "mark", "stream": self.endpoint, "through": t, "arrived": now})

    def on_message(self, msg: dict) -> None:
        if not isinstance(msg, dict):
            return
        if self._reconnected(msg):
            self.new_stream()                    # the provider reconnected inside this stream: its turns from 0 again
        if msg.get("type") != "TurnInfo":
            return
        self.seen += 1
        self.last_msg_ms, self.stall_said = _now_ms(), False
        self.last_turn = int(msg.get("turn_index") or 0)
        self.last_end = float(msg.get("audio_window_end") or 0.0)
        end = msg.get("event") == ear_feed.END
        self.heard = () if end else tuple(str(w.get("word") or "") for w in msg.get("words") or ())
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
            self.tap.provider_quiet(now)
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
            # His voice rose while ours sounded, so its rise went out as possible echo and the ear did not open it. It
            # just proved it is his (after our line began, past the threshold): the ear hears it from its real start —
            # a barge-in with no word then ends discarded, and the line it cut goes on (RESUME_LINE). A rise right at
            # our line's start is how our own echo rises with no echo cancellation: never sent again as his.
            if self.rose_at - self.tap.playing_since >= ECHO_ONSET_MS:
                self.tap.send(ear_feed.vad(self.tap.endpoint, "rise", self.rose_at, echo_safe=True))


def _barge_due(edges: "VadEdges", now: int) -> bool:
    """His voice rose after our line began and lasted `min_barge_ms`: it cuts on his WORDS, and only when they are not
    our own line coming back — an echo never cuts it. With no words it never cuts: a rise alone cannot tell our echo
    (it reaches the microphone after the playout's own delay, and the provider's first words after that) from his
    «mmm», and a «mmm» over our line lets it go on."""
    tap = edges.tap
    if not (tap.speaking and tap.on_barge is not None and not edges.cut and tap.playing_since is not None
            and edges.rose_at >= tap.playing_since and now - edges.rose_at >= tap.min_barge_ms):
        return False
    from voice import echo_text
    return len(echo_text.tokens(tap.heard)) >= echo_text.MIN_WORDS and not echo_text.contained(tap.heard, tap.line)


def titular(stt):
    """The provider whose own messages the ear reads: the STT itself, or the first one a fallback adapter wraps (the
    adapter calls `stream()` on each of them in turn, so a tap on the titular sees every message it sends, whatever
    wraps it). None when it has no message handler to tap — the session is then not the manager's."""
    inner = (getattr(stt, "_stt_instances", None) or [stt])[0]
    stream_class = getattr(inner, "_zaelar_stream_class", None) or _stream_class(inner)
    return inner if stream_class is not None and hasattr(stream_class, "_process_stream_event") else None


def _stream_class(stt):
    from livekit.plugins.deepgram import stt_v2
    return stt_v2.SpeechStreamv2 if isinstance(stt, stt_v2.STTv2) else None


def install_stt(stt, tap: Tap):
    """Every stream the TITULAR opens hands its raw messages to `tap` first, then to the plugin as before; after an end
    of turn the session's own turn is cleared (`tap.on_end`: nothing of LiveKit's accumulates). Each stream has its own
    clock and turns. It fails OPEN: a stream with no message handler is left as it is and said, never broken.

    Behind a fallback adapter the stand-in has no turns of its own: when the titular falls, the ear is told (`gap`:
    what it was hearing ends incomplete) and, until the titular is back, the stand-in's FINAL transcripts are its words
    and ends (`Tap.final_transcript`). The STT may be the process's warm one: `uninstall` gives it back."""
    uninstall(stt)
    inner = titular(stt)
    if inner is None:
        return stt
    open_stream = inner.stream

    def stream(*a, **kw):
        s = open_stream(*a, **kw)
        original = getattr(s, "_process_stream_event", None)
        if original is None:                     # fail open: the provider's own path, untouched
            logger.warning(f"ear tap: {type(s).__name__} has no message handler; not tapped")
            return s
        if inner is not stt:                     # behind an adapter: a recovery stream is never heard
            if not tap.titular_opened():
                return s
        else:
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

    inner.stream = stream
    inner._zaelar_ear_stream = open_stream
    if inner is not stt and hasattr(stt, "on"):
        def changed(ev) -> None:
            if getattr(ev, "stt", None) is inner:
                tap.titular_available(bool(getattr(ev, "available", True)))
        stt.on("stt_availability_changed", changed)
        stt._zaelar_ear_changed = changed
    return stt


def uninstall(stt) -> None:
    inner = (getattr(stt, "_stt_instances", None) or [stt])[0]
    open_stream = getattr(inner, "_zaelar_ear_stream", None)
    if open_stream is not None:
        inner.stream = open_stream
        del inner._zaelar_ear_stream
    changed = getattr(stt, "_zaelar_ear_changed", None)
    if changed is not None:
        stt.off("stt_availability_changed", changed)
        del stt._zaelar_ear_changed


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

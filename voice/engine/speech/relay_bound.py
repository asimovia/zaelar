"""The relay's bound on a provider that HANGS instead of failing (V2-896 P1-4): LiveKit bounds only a pool's wait, so
a voice connected and mute was ~140 s of silence and a hung handshake up to 300 s. Declared in `relay_bound`
(`config/resources.default.json`). Voice, titular only, until its first audio: none `tts_first_byte_s` after the
sentence reached it (its stream's `_started_time` — the first token's clock would measure the brain), or no sentence
sent `tts_ready_s` after one was ready → down, no retry. Ear: `stt_strikes` spans ≥ `stt_span_s` with no STT event
within `stt_answer_s`. `shadow` says what it WOULD do; `armed` switches the voice (the ear stays shadow).
"""
from __future__ import annotations

import asyncio
import dataclasses
import time

_TICK_S = 0.1


@dataclasses.dataclass(frozen=True)
class Bound:
    """`relay_bound` as declared (`config/resources.default.json`); a field the file omits keeps its value here."""
    mode: str = "shadow"
    tts_first_byte_s: float = 2.0
    tts_ready_s: float = 3.0
    stt_span_s: float = 0.6
    stt_answer_s: float = 2.5
    stt_strikes: int = 2


@dataclasses.dataclass
class _Ear:
    start: float = 0.0
    heard_at: float = 0.0
    strikes: int = 0
    pending: list = dataclasses.field(default_factory=list)


_EAR = _Ear()


def policy() -> Bound:
    from nucleo.workers import envelope       # reads the declared files; an unreadable one is said there
    declared = envelope.policy().get("relay_bound") or {}
    return Bound(**{f.name: declared[f.name] for f in dataclasses.fields(Bound) if f.name in declared})


def _say(family: str, provider: str, why: str) -> None:
    from voice.observer import emit
    emit("provider", f"🕳️ {family.upper()} «{provider}» would switch (shadow): {why}", role="system",
         extra={"cat": family, "provider": provider, "would_switch": True, "why": why})


def _late(gen, outer, pol: Bound, clock: dict) -> str:
    """Why the titular is late for its first audio, or ''."""
    now = time.perf_counter()
    frame = getattr(gen, "ag_frame", None)
    inner = frame.f_locals.get("stream") if frame is not None else None
    started = float(getattr(inner, "_started_time", 0) or 0)
    if started:
        fb = float(pol.tts_first_byte_s)
        return f"no first audio {fb:g} s after the sentence reached it" if now - started > fb else ""
    if not clock.get("ready"):
        text = "".join(getattr(outer, "_pushed_tokens", ()) or ())
        if text.strip() and (outer._input_ch.closed or _two_sentences(text)):
            clock["ready"] = now
    rs = float(pol.tts_ready_s)
    return f"no sentence sent {rs:g} s after one was ready" if clock.get("ready") and now - clock["ready"] > rs else ""


def _two_sentences(text: str) -> bool:
    from livekit.agents import tokenize
    return len(tokenize.blingfire.SentenceTokenizer(retain_format=True).tokenize(text)) > 1


async def first_audio(gen, outer, provider: str):
    """`gen`'s audio, watched until its first frame. Armed: a late titular is closed and raised as a timeout (the
    adapter marks it down and the stand-in speaks the same text); shadow: said once, and nothing changes."""
    from livekit.agents import APITimeoutError
    pol, clock, said = policy(), {}, False
    nxt = asyncio.ensure_future(gen.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({nxt}, timeout=_TICK_S)
            if nxt in done:
                break
            why = "" if said else _late(gen, outer, pol, clock)
            if not why:
                continue
            said = True
            if pol.mode != "armed":
                _say("tts", provider, why)
                continue
            nxt.cancel()
            await asyncio.wait({nxt})               # the attempt closes; the timeout below is the verdict
            raise APITimeoutError(why)
        if isinstance(nxt.exception(), StopAsyncIteration):
            return                                  # the titular ended without a frame: LiveKit's own «no audio» follows
        yield nxt.result()
        async for audio in gen:
            yield audio
    finally:
        if not nxt.done():
            nxt.cancel()
            await asyncio.wait({nxt})
        await gen.aclose()


def ear_heard() -> None:
    """Any STT event (an interim counts): the ear answered."""
    _EAR.heard_at = time.monotonic()
    _judge(_EAR.heard_at)


def ear_state(state: str) -> None:
    """The VAD's speech spans (read where the session's events are handled, the body in both topologies). A span of at
    least `stt_span_s` is judged once `stt_answer_s` passed after it — lazily, at the next event: no timer, no loop."""
    now = time.monotonic()
    _judge(now)
    if state == "speaking":
        _EAR.start = now
        return
    start, _EAR.start = _EAR.start, 0.0
    if state == "listening" and start and now - start >= float(policy().stt_span_s):
        _EAR.pending.append((start, now))


def _judge(now: float) -> None:
    if not _EAR.pending:
        return
    pol, keep = policy(), []
    for start, end in _EAR.pending:
        if start <= _EAR.heard_at <= end + float(pol.stt_answer_s):
            _EAR.strikes = 0
        elif now > end + float(pol.stt_answer_s):
            _EAR.strikes += 1
        else:
            keep.append((start, end))
    _EAR.pending = keep
    if _EAR.strikes >= int(pol.stt_strikes):
        from ..core.config import SETTINGS
        _EAR.strikes = 0
        _say("stt", SETTINGS.stt_provider, f"{int(pol.stt_strikes)} speech spans of ≥{float(pol.stt_span_s):g} s "
                                           f"with no word from it within {float(pol.stt_answer_s):g} s")

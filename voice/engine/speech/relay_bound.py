"""The relay's bound on a provider that HANGS instead of failing (V2-896 P1-4).

A refused or failed call switches on its own; a hung one never raises. LiveKit's clocks bound only a pool's capacity
wait: a voice connected and mute waited ~70 s per attempt, retried on the same socket (140 s measured), and a hung
handshake waits for the HTTP client's total (300 s). The bound, declared as data (`relay_bound`,
`config/resources.default.json`):
  · voice (the titular only, until its first audio): no audio `tts_first_byte_s` after the sentence reached it (its
    stream's own `_started_time`, never the first token: that clock measures the brain), or no sentence sent
    `tts_ready_s` after one was ready (a hung handshake) → down, with NO retry on the same socket;
  · ear: `stt_strikes` speech spans in a row of at least `stt_span_s` with no STT event within `stt_answer_s`.
`mode: shadow` says what it WOULD do (a `provider` event) and changes nothing — the rule is bound ≥ 1.5 × the fleet's
p99.9 TTFB, unmeasured yet. `armed` makes the voice switch; the ear stays shadow (switching a live ear stream is not
built).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

_DEFAULTS = {"mode": "shadow", "tts_first_byte_s": 2.0, "tts_ready_s": 3.0, "stt_span_s": 0.6, "stt_answer_s": 2.5,
             "stt_strikes": 2}
_TICK_S = 0.1
_EAR: dict = {"start": 0.0, "heard_at": 0.0, "strikes": 0, "pending": []}


def policy() -> dict:
    try:
        from nucleo.workers import envelope
        return {**_DEFAULTS, **(envelope.policy().get("relay_bound") or {})}
    except Exception as e:  # noqa: BLE001 — an unreadable policy keeps the defaults, said
        logger.debug(f"relay_bound: policy unreadable ({e!r}) — defaults")
        return dict(_DEFAULTS)


def _say(family: str, provider: str, why: str) -> None:
    from voice.observer import emit
    emit("provider", f"🕳️ {family.upper()} «{provider}» would switch (shadow): {why}", role="system",
         extra={"cat": family, "provider": provider, "would_switch": True, "why": why})


def _late(gen, outer, pol: dict, clock: dict) -> str:
    """Why the titular is late for its first audio, or ''."""
    now = time.perf_counter()
    frame = getattr(gen, "ag_frame", None)
    inner = frame.f_locals.get("stream") if frame is not None else None
    started = float(getattr(inner, "_started_time", 0) or 0)
    if started:
        fb = float(pol["tts_first_byte_s"])
        return f"no first audio {fb:g} s after the sentence reached it" if now - started > fb else ""
    if not clock.get("ready"):
        text = "".join(getattr(outer, "_pushed_tokens", ()) or ())
        if text.strip() and (outer._input_ch.closed or _two_sentences(text)):
            clock["ready"] = now
    rs = float(pol["tts_ready_s"])
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
            if pol["mode"] != "armed":
                _say("tts", provider, why)
                continue
            nxt.cancel()
            try:
                await nxt
            except BaseException:  # noqa: BLE001 — the cancelled attempt; the timeout below is the verdict
                pass
            raise APITimeoutError(why)
        try:
            first = nxt.result()
        except StopAsyncIteration:
            return
        yield first
        async for audio in gen:
            yield audio
    finally:
        if not nxt.done():
            nxt.cancel()
            try:
                await nxt
            except BaseException:  # noqa: BLE001 — closing; whatever the attempt ended in was already read
                pass
        await gen.aclose()


def ear_heard() -> None:
    """Any STT event (an interim counts): the ear answered."""
    _EAR["heard_at"] = time.monotonic()
    _judge(_EAR["heard_at"])


def ear_state(state: str) -> None:
    """The VAD's speech spans (read where the session's events are handled, the body in both topologies). A span of at
    least `stt_span_s` is judged once `stt_answer_s` passed after it — lazily, at the next event: no timer, no loop."""
    now = time.monotonic()
    _judge(now)
    if state == "speaking":
        _EAR["start"] = now
        return
    start, _EAR["start"] = _EAR["start"], 0.0
    if state == "listening" and start and now - start >= float(policy()["stt_span_s"]):
        _EAR["pending"].append((start, now))


def _judge(now: float) -> None:
    if not _EAR["pending"]:
        return
    pol, keep = policy(), []
    for start, end in _EAR["pending"]:
        if start <= _EAR["heard_at"] <= end + float(pol["stt_answer_s"]):
            _EAR["strikes"] = 0
        elif now > end + float(pol["stt_answer_s"]):
            _EAR["strikes"] += 1
        else:
            keep.append((start, end))
    _EAR["pending"] = keep
    if _EAR["strikes"] >= int(pol["stt_strikes"]):
        from ..core.config import SETTINGS
        _EAR["strikes"] = 0
        _say("stt", SETTINGS.stt_provider, f"{int(pol['stt_strikes'])} speech spans of ≥{float(pol['stt_span_s']):g} s "
                                           f"with no word from it within {float(pol['stt_answer_s']):g} s")

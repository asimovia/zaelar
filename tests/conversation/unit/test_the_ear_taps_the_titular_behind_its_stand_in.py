"""The ear taps the TITULAR provider, whatever wraps it, and fails open (node 13.92, V2-941, v3.1 §1.7, B8c).

The voice smoke (3b) found the manager never running: since the session's ear became a fallback adapter (the titular
and a stand-in), the tap patched the ADAPTER's stream, which has no message handler, and broke the provider's pump.
Now, with the real adapter:
  · the tap is on the titular inside it — the adapter opens the titular's stream, so every message of the titular is
    tapped; the adapter's own stream and the stand-in's are untouched;
  · a stream with no message handler is left as it is (fail open), and an STT whose titular cannot be tapped makes the
    session the old path's (`titular` None);
  · when the titular falls, what the ear was hearing ends incomplete (a declared `gap`) and, until it is back, the
    stand-in's FINAL transcripts are the ear's words and ends — numbered apart from the titular's turns;
  · `uninstall` gives the warm STT back as it was.
"""
from __future__ import annotations

import asyncio

import aiohttp
from livekit.agents.stt import AvailabilityChangedEvent, FallbackAdapter
from livekit.plugins.deepgram import STT, stt_v2

from voice.engine.pipeline import ear_feed, ear_tap

MSG = {"type": "TurnInfo", "event": ear_feed.UPDATE, "turn_index": 0, "audio_window_start": 0.0,
       "audio_window_end": 1.0, "words": [{"word": "w1", "start": 0.1, "end": 0.3, "confidence": 0.9}],
       "transcript": "w1"}


def _with_adapter(body):
    async def go():
        async with aiohttp.ClientSession() as http:
            flux, stand = stt_v2.STTv2(api_key="w_key", http_session=http), STT(api_key="w_key", http_session=http)
            adapter = FallbackAdapter([flux, stand], max_retry_per_stt=1)
            facts = []
            tap = ear_tap.Tap("holder", facts.append)
            try:
                return await body(adapter, flux, stand, tap, facts)
            finally:
                ear_tap.uninstall(adapter)
    return asyncio.run(go())


def test_the_tap_is_on_the_titular_and_never_on_what_wraps_it():
    async def body(adapter, flux, stand, tap, facts):
        stand_open = stand.stream
        ear_tap.install_stt(adapter, tap)
        assert ear_tap.titular(adapter) is flux and stand.stream == stand_open
        s = flux.stream()
        s._process_stream_event(MSG)
        await s.aclose()
        wrapper = adapter.stream()                                               # the adapter's own: not broken
        await wrapper.aclose()
        return [f["t"] for f in facts]
    assert _with_adapter(body) == ["words", "mark"]


def test_when_the_titular_falls_the_gap_is_declared_and_the_stand_ins_finals_are_heard():
    async def body(adapter, flux, stand, tap, facts):
        ear_tap.install_stt(adapter, tap)
        main = flux.stream()                                                     # the session's main stream
        tap.final_transcript("w0")                                               # the titular is main: not these
        adapter.emit("stt_availability_changed", AvailabilityChangedEvent(stt=flux, available=False))
        tap.final_transcript("w2 w3.", now_ms=5000)
        adapter.emit("stt_availability_changed", AvailabilityChangedEvent(stt=flux, available=True))
        tap.final_transcript("w4")                                               # up again, the stand-in still MAIN
        await main.aclose()
        return facts
    facts = [f for f in _with_adapter(body) if f["t"] != "mark" or True]
    words = [f for f in facts if f["t"] == "words"]
    assert [f["t"] for f in facts][:2] == ["gap", "words"] and [[w[0] for w in f["words"]] for f in words] == \
        [["w2", "w3."], ["w4"]]                                                   # never deaf after the way back
    eot = next(f for f in facts if f["t"] == "eot")
    assert words[0]["turn"] > ear_tap.STAND_IN_TURNS and eot["kind"] == "end" and eot["terminal"] is True


def test_a_recovery_stream_is_never_heard_and_the_titular_is_main_again_only_when_it_opens():
    """TI-1: while the titular is down the adapter opens a RECOVERY stream on it, fed the same audio — never heard
    (each sentence would reach the ear twice, and its opening would cut what the stand-in was hearing). Up again, the
    next stream of the titular is the main one: the stand-in is read no more."""
    async def body(adapter, flux, stand, tap, facts):
        ear_tap.install_stt(adapter, tap)
        main = flux.stream()
        adapter.emit("stt_availability_changed", AvailabilityChangedEvent(stt=flux, available=False))
        recovery = flux.stream()                                                 # what `_try_recovery` opens
        tap.final_transcript("w1 w2", now_ms=5000)
        recovery._process_stream_event(MSG)                                      # the same audio: never heard
        gaps = sum(f["t"] == "gap" for f in facts)
        adapter.emit("stt_availability_changed", AvailabilityChangedEvent(stt=flux, available=True))
        await recovery.aclose()
        again = flux.stream()                                                    # the next main stream, the titular's
        again._process_stream_event(MSG)
        tap.final_transcript("w9")                                               # the stand-in: read no more
        await again.aclose()
        await main.aclose()
        return facts, gaps
    facts, gaps = _with_adapter(body)
    words = [" ".join(w[0] for w in f["words"]) for f in facts if f["t"] == "words"]
    assert words == ["w1 w2", "w1"] and gaps == 1                               # once each, and one gap at the fall


def test_a_reconnect_inside_one_stream_is_a_new_epoch_with_its_own_clock():
    """TI-2: the provider's websocket reconnects inside one stream: `Connected` again, its turns and its audio clock
    from 0. The ear takes what follows as a new stream: a new epoch, a new clock, a gap."""
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    tap.new_stream()
    tap.on_message({**MSG, "audio_window_end": 9.0, "turn_index": 3})
    first = tap.epoch
    tap.on_message({"type": "Connected"})
    tap.on_message(MSG)                                                          # turn 0, window from 0
    assert tap.epoch > first and [f["t"] for f in facts].count("gap") == 1
    tap2 = ear_tap.Tap("holder", facts.append)
    tap2.new_stream()
    tap2.on_message({**MSG, "turn_index": 5, "audio_window_end": 20.0})
    e = tap2.epoch
    tap2.on_message({**MSG, "turn_index": 0, "audio_window_end": 0.3})          # backwards with no `Connected`
    assert tap2.epoch > e


def test_it_fails_open_and_gives_the_stt_back():
    class _Bare:
        def __init__(self):
            self.opened = []

        def stream(self, *a, **kw):
            s = object()
            self.opened.append(s)
            return s

    bare = _Bare()
    bare._zaelar_stream_class = type("Declared", (), {"_process_stream_event": lambda self, data: None})
    # …declared tappable, yet the stream it opens has no handler
    bare_stream = bare.stream
    tap = ear_tap.Tap("holder", lambda f: None)
    ear_tap.install_stt(bare, tap)
    assert ear_tap.titular(bare) is bare and bare.stream != bare_stream          # it was tapped
    assert bare.stream() is bare.opened[-1]                                      # its stream untouched, never broken
    ear_tap.uninstall(bare)
    assert bare.stream == bare_stream

    async def body(adapter, flux, stand, tap, facts):
        assert ear_tap.titular(stand) is None                                   # no message handler: the old path
        flux_open = flux.stream
        ear_tap.install_stt(adapter, tap)
        ear_tap.uninstall(adapter)
        return flux.stream == flux_open and not hasattr(adapter, "_zaelar_ear_changed")
    assert _with_adapter(body)

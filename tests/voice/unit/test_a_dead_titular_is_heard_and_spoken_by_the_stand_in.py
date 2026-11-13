"""V2-896 — kill the titular and the agent still hears and speaks, through the stand-in, and SAYS why.

The ear and the voice are built by the engine's own `build_stt()` / `build_tts()` (LiveKit's real `FallbackAdapter`),
with plugin doubles: a titular that refuses every connection and a stand-in that answers. Then:

  · the session's stream yields the STAND-IN's audio / transcript, never silence;
  · the switch alert names the titular's ERROR (a stand-in that took over without saying why would hide a defect of
    ours — a socket closed on silence — exactly as well as an outage);
  · the stand-in's usage is billed to the stand-in (its plugin label), not to the titular the settings select;
  · `active_provider()` names the one serving.

Disarm (measured 2026-11-13): returning the titular alone from either builder leaves the stream empty (red); dropping
the cause from the alert reds the attribution asserts; billing by the selected provider reds the meter asserts.
"""
from __future__ import annotations

import asyncio
import dataclasses

import pytest
from livekit import rtc
from livekit.agents import APIConnectionError, stt as lk_stt, tts as lk_tts
from livekit.agents.metrics import STTMetrics, TTSMetrics

from voice.engine.pipeline import metrics_tap
from voice.engine.speech import relay, stt as S, tts as T

RATE = 24000
EMITTED: list = []
_PCM = (b"\x10\x27" * (RATE // 5))          # 200 ms of a constant, recognisable sample


# ── the voice ─────────────────────────────────────────────────────────────────────────────────────────────────────
class _Chunk(lk_tts.ChunkedStream):
    def __init__(self, *, tts, input_text, conn_options, dead):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._dead = dead

    async def _run(self, out) -> None:
        if self._dead:
            raise APIConnectionError("connection refused by the titular voice")
        out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm")
        out.push(_PCM)
        out.flush()


class _Voice(lk_tts.TTS):
    def __init__(self, dead: bool):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=False), sample_rate=RATE, num_channels=1)
        self._dead = dead
        self._label = f"doubles.{'dead' if dead else 'live'}_voice.TTS"

    def synthesize(self, text, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
        return _Chunk(tts=self, input_text=text, conn_options=conn_options, dead=self._dead)


# ── the ear ───────────────────────────────────────────────────────────────────────────────────────────────────────
class _Stream(lk_stt.RecognizeStream):
    def __init__(self, *, stt, conn_options, dead):
        super().__init__(stt=stt, conn_options=conn_options, sample_rate=16000)
        self._dead = dead

    async def _run(self) -> None:
        if self._dead:
            raise APIConnectionError("connection closed by the titular ear")
        heard = 0
        async for item in self._input_ch:
            if isinstance(item, rtc.AudioFrame):
                heard += 1
        E = lk_stt.SpeechEventType
        self._event_ch.send_nowait(lk_stt.SpeechEvent(type=E.FINAL_TRANSCRIPT, alternatives=[
            lk_stt.SpeechData(language="es", text=f"te oigo desde el relevo ({heard} frames)")]))
        self._event_ch.send_nowait(lk_stt.SpeechEvent(type=E.RECOGNITION_USAGE,
                                                      recognition_usage=lk_stt.RecognitionUsage(audio_duration=1.0)))


class _Ear(lk_stt.STT):
    def __init__(self, dead: bool):
        super().__init__(capabilities=lk_stt.STTCapabilities(streaming=True, interim_results=True,
                                                             aligned_transcript="word"))
        self._dead = dead
        self._label = f"doubles.{'dead' if dead else 'live'}_ear.STT"

    async def _recognize_impl(self, buffer, **kw):  # pragma: no cover — the session streams
        raise NotImplementedError

    def stream(self, *, language=None, conn_options=lk_stt.stt.DEFAULT_API_CONNECT_OPTIONS):
        return _Stream(stt=self, conn_options=conn_options, dead=self._dead)


@pytest.fixture
def world(monkeypatch):
    """Titular deepgram/inworld, stand-in openai — as the table names them — each built as a double."""
    said: list = []
    billed: list = []
    monkeypatch.setattr(relay, "_STATE", {})
    EMITTED.clear()                                      # what the body's observer says, kept off the durable log
    import voice.observer
    monkeypatch.setattr(voice.observer, "emit", lambda kind, label, **kw: EMITTED.append((kind, label, kw)))
    for fam, titular in ((S, "deepgram"), (T, "inworld")):
        monkeypatch.setattr(fam.registry, "_builders", dict(fam.registry._builders))
        monkeypatch.setattr(fam, "_note", lambda msg, _fam=fam, **extra: said.append((msg, extra)))
    monkeypatch.setattr(S, "SETTINGS", dataclasses.replace(S.SETTINGS, stt_provider="deepgram"))
    monkeypatch.setattr(T, "SETTINGS", dataclasses.replace(T.SETTINGS, tts_provider="inworld"))
    monkeypatch.setattr(metrics_tap, "SETTINGS", dataclasses.replace(metrics_tap.SETTINGS, stt_provider="deepgram",
                                                                     tts_provider="inworld"))
    from config import models
    monkeypatch.setattr(models, "failover", lambda name: {"provider": "openai"} if name in ("stt", "tts") else None)
    S.registry._builders["deepgram"] = lambda vad=None: _Ear(dead=True)
    S.registry._builders["openai"] = lambda vad=None: _Ear(dead=False)
    T.registry._builders["inworld"] = lambda: _Voice(dead=True)
    T.registry._builders["openai"] = lambda: _Voice(dead=False)
    from nucleo.energy import meter
    monkeypatch.setattr(meter, "report_stt_usage", lambda **kw: billed.append(("stt", kw["provider"])))
    monkeypatch.setattr(meter, "report_tts_usage", lambda **kw: billed.append(("tts", kw["provider"])))
    return said, billed


def _meter(adapter, sink: list):
    adapter.on("metrics_collected", lambda m: sink.append(m))


def _bill_in_the_body(m) -> None:
    """The real seam (P1-1): the voice process turns the metric into fields (`child_session._metric_fields`, where the
    adapter lives) and the BODY replays them (`remote_session.handle`), with none of the voice process's state."""
    from voice import remote_session
    from voice.engine.pipeline import child_session
    fields = child_session._metric_fields(m)
    held, session = dict(relay._STATE), remote_session._M["session"]
    relay._STATE.clear()                                 # the body never built the adapter
    remote_session._M["session"] = object()              # a session the body saw start
    try:
        remote_session.handle({"k": "metrics", **fields})
    finally:
        relay._STATE.update(held)
        remote_session._M["session"] = session


def test_a_dead_voice_is_spoken_by_the_stand_in_and_the_switch_says_why(world):
    said, billed = world
    voice = T.build_tts()
    metrics: list = []
    _meter(voice, metrics)

    async def speak() -> bytes:
        out = bytearray()
        async with voice.stream() as s:
            s.push_text("Hola, sigo aquí.")
            s.end_input()
            async for ev in s:
                out += ev.frame.data.tobytes()
        return bytes(out)

    audio = asyncio.run(asyncio.wait_for(speak(), 10))
    assert audio and set(audio[:len(_PCM)]) == set(_PCM), "the session must hear the stand-in's audio, not silence"
    assert T.active_provider() == "openai"
    jump = [x for m, x in said if x.get("stand_in") == "openai" and x.get("provider") == "inworld"]
    assert jump and "connection refused by the titular voice" in jump[-1]["cause"], \
        "a switch must name the titular's error — never a silent mask"
    for m in metrics:
        if isinstance(m, TTSMetrics) and m.characters_count:
            _bill_in_the_body(m)
    assert ("tts", "openai") in billed and ("tts", "inworld") not in billed, \
        "the stand-in's characters are billed at the stand-in's rate"


def test_a_dead_ear_is_heard_by_the_stand_in_and_the_switch_says_why(world):
    said, billed = world
    ear = S.build_stt(vad=None)
    metrics: list = []
    _meter(ear, metrics)
    frame = rtc.AudioFrame(data=b"\x00\x01" * 160, sample_rate=16000, num_channels=1, samples_per_channel=160)

    async def listen() -> list[str]:
        texts: list[str] = []
        s = ear.stream()
        async with s:
            await asyncio.sleep(0.3)             # the titular refuses, retries once, and the adapter switches
            for _ in range(5):
                s.push_frame(frame)
            s.end_input()
            async for ev in s:
                if ev.type == lk_stt.SpeechEventType.FINAL_TRANSCRIPT:
                    texts.append(ev.alternatives[0].text)
        return texts

    texts = asyncio.run(asyncio.wait_for(listen(), 10))
    assert texts and texts[0].startswith("te oigo desde el relevo"), "the agent must hear through the stand-in"
    assert S.active_provider() == "openai"
    jump = [x for m, x in said if x.get("stand_in") == "openai" and x.get("provider") == "deepgram"]
    assert jump and "connection closed by the titular ear" in jump[-1]["cause"], \
        "a switch must name the titular's error — a socket closed on silence must not pass for an outage"
    for m in metrics:
        if isinstance(m, STTMetrics):
            _bill_in_the_body(m)
    assert ("stt", "openai") in billed and ("stt", "deepgram") not in billed, \
        "the stand-in's audio is billed at the stand-in's rate, not the titular's"


def test_an_unused_relay_bills_and_labels_the_titular(world, monkeypatch):
    """Nothing failed: the titular's metric is the titular's — the relay adds no attribution of its own."""
    _, billed = world
    T.registry._builders["inworld"] = lambda: _Voice(dead=False)
    voice = T.build_tts()
    m = TTSMetrics(label=voice._tts_instances[0].label, request_id="r", timestamp=0.0, ttfb=0.1, duration=0.2,
                   audio_duration=0.2, cancelled=False, characters_count=12, streamed=False)
    _bill_in_the_body(m)
    assert billed == [("tts", "inworld")] and T.active_provider() == "inworld"


def test_the_titulars_own_probe_is_billed_to_the_titular_while_the_stand_in_serves(world):
    """P2-1 — the label, not who is serving: with the stand-in active, a metric the TITULAR produced (its recovery
    probe) is the titular's; two providers on one plugin class cannot be told apart, so it falls to the one serving."""
    _, billed = world
    voice = T.build_tts()
    relay.set_active("tts", "openai")
    titular = voice._tts_instances[0]

    def metric(label):
        return TTSMetrics(label=label, request_id="r", timestamp=0.0, ttfb=0.1, duration=0.2, audio_duration=0.2,
                          cancelled=False, characters_count=12, streamed=False)
    _bill_in_the_body(metric(titular.label))
    assert billed == [("tts", "inworld")]
    relay.track("tts", [("inworld", titular), ("elevenlabs", titular)])   # one class, two names: the label clashes
    relay.set_active("tts", "elevenlabs")
    _bill_in_the_body(metric(titular.label))
    assert billed[-1] == ("tts", "elevenlabs")


# ── the relay unused: nothing held back ───────────────────────────────────────────────────────────────────────────
class _Flowing(lk_tts.SynthesizeStream):
    """A healthy streaming titular that releases every chunk as it makes it (Inworld's PCM flushes after each push)."""

    async def _run(self, out) -> None:
        out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm", stream=True)
        out.start_segment(segment_id="s")
        async for d in self._input_ch:
            if isinstance(d, str) and d.strip():
                for _ in range(7):                       # 7 × 30 ms: a sentence that is not a whole 200 ms frame
                    out.push(b"\x01\x00" * (RATE * 30 // 1000))
                    out.flush()
        out.end_segment()


class _FlowingVoice(lk_tts.TTS):
    def __init__(self):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=True), sample_rate=RATE, num_channels=1)

    def synthesize(self, text, **kw):  # pragma: no cover — the session streams
        raise NotImplementedError

    def stream(self, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
        return _Flowing(tts=self, conn_options=conn_options)


def test_an_unused_relay_holds_no_audio_back(world):
    """With the stand-in unused, a sentence's whole audio reaches the session before the next sentence exists. The
    stock adapter re-cut it into 200 ms frames and held the partial tail until more audio came (measured: ~440 ms
    of a sentence's end waiting for the next one)."""
    T.registry._builders["inworld"] = lambda: _FlowingVoice()
    voice = T.build_tts()
    want = 7 * (RATE * 30 // 1000)

    async def first_sentence() -> int:
        got = 0
        async with voice.stream() as s:
            s.push_text("Una frase entera.")
            it = s.__aiter__()
            try:
                while got < want:
                    ev = await asyncio.wait_for(it.__anext__(), 0.5)
                    raw = ev.frame.data.tobytes()
                    got += sum(1 for i in range(0, len(raw), 2) if raw[i] == 1)
            except asyncio.TimeoutError:
                pass
            s.end_input()
            async for _ in s:
                pass
        return got

    got = asyncio.run(asyncio.wait_for(first_sentence(), 10))
    assert got >= want, f"the session got {got} of {want} samples of the first sentence — the relay held its tail"


# ── the titular comes back (P1-3) ─────────────────────────────────────────────────────────────────────────────────
_T, _B = b"\x01\x00", b"\x02\x00"          # titular samples, stand-in samples


class _Scripted(lk_tts.SynthesizeStream):
    """A streaming titular that plays the next entry of its script per connection: refuse, cut mid-sentence, or ok."""

    def __init__(self, *, tts, conn_options, mode):
        super().__init__(tts=tts, conn_options=conn_options)
        self._mode = mode

    async def _run(self, out) -> None:
        out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm", stream=True)
        if self._mode == "refuse":
            raise APIConnectionError("connection refused")
        if self._mode == "bug":
            raise RuntimeError("a defect of ours")       # no APIError: the plugin's `error` event never fires
        out.start_segment(segment_id="s")
        async for d in self._input_ch:
            if isinstance(d, str) and d.strip() and self._mode != "mute":
                self._mark_started()
                out.push(_T * (RATE // 10))
                out.flush()
                if self._mode == "cut":
                    await asyncio.sleep(0.02)
                    raise APIConnectionError("socket closed mid-sentence")
        out.end_segment()


class _ScriptedVoice(lk_tts.TTS):
    def __init__(self, script: list):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=True), sample_rate=RATE, num_channels=1)
        self._script = script
        self._label = "doubles.scripted_voice.TTS"

    def synthesize(self, text, **kw):  # pragma: no cover — the session streams
        raise NotImplementedError

    def stream(self, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
        return _Scripted(tts=self, conn_options=conn_options, mode=self._script.pop(0) if self._script else "ok")


class _StandIn(lk_tts.TTS):
    def __init__(self):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=False), sample_rate=RATE, num_channels=1)

    def synthesize(self, text, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
        tts = self

        class _C(lk_tts.ChunkedStream):
            async def _run(self, out) -> None:
                out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm")
                out.push(_B * (RATE // 10))
                out.flush()
        return _C(tts=tts, input_text=text, conn_options=conn_options)


def _sentences(script: list, n: int, said: list) -> list[str]:
    voice = T._with_failover([("inworld", _ScriptedVoice(script)), ("openai", _StandIn())])

    async def one() -> str:
        heard: set = set()
        async with voice.stream() as s:
            s.push_text("Una frase entera. ")
            s.end_input()
            async for ev in s:
                raw = ev.frame.data.tobytes()
                heard |= {raw[i:i + 2] for i in range(0, len(raw), 2)} - {b"\x00\x00"}
        await asyncio.sleep(0.2)                         # a probe runs in the background between turns
        return "+".join(sorted({_T: "titular", _B: "stand-in"}[x] for x in heard))

    async def all_of_them() -> list[str]:
        return [await one() for _ in range(n)]
    return asyncio.run(asyncio.wait_for(all_of_them(), 20))


def test_a_voice_cut_mid_sentence_comes_back_at_the_next_turn(world):
    """Before: the titular ran once, cut, and never again — the stand-in spoke until the process restarted."""
    said, _ = world
    served = _sentences(["cut"], 4, said)
    assert served[0] == "titular" and served[-1] == "titular", served
    assert any("is back" in m for m, _ in said) and T.active_provider() == "inworld"


def test_a_voice_refused_three_times_is_back_once_it_answers(world):
    """Two refusals on the first turn (an attempt and its retry), the third on the probe: the probe of the NEXT turn
    finds it healthy, says so, and the turn after is the titular's."""
    said, _ = world
    served = _sentences(["refuse", "refuse", "refuse"], 4, said)
    assert served[0] == "stand-in" and served[-1] == "titular", served
    assert sum("is back" in m for m, _ in said) == 1


# ── the cause of a switch (P1-2) ──────────────────────────────────────────────────────────────────────────────────
def _alerts(said: list) -> list[str]:
    return [x["cause"] for _, x in said if "cause" in x]


def test_a_cause_is_one_episodes_and_never_carries_the_spoken_words(world):
    """Episode 1 refused → back → episode 2 a defect of ours: the second alert names the defect, not the first
    refusal. A titular that answers with no audio: LiveKit's error quotes the sentence — the alert must not."""
    said, _ = world
    _sentences(["refuse", "refuse", "ok", "bug"], 4, said)
    causes = _alerts(said)
    assert len(causes) == 2 and "connection refused" in causes[0] and "RuntimeError: a defect of ours" == causes[1], said
    said.clear()
    _sentences(["mute", "mute"], 1, said)
    assert _alerts(said) and all("Una frase" not in c for c in _alerts(said)), _alerts(said)


def _real_inworld_against(handler) -> dict:
    """The REAL Inworld plugin, pointed at a local server, as the titular; the stand-in a double."""
    import time

    import aiohttp
    from aiohttp import web
    from livekit.plugins import inworld

    out = {"stand_in_audio": 0, "s": 0.0}

    async def run() -> None:
        port = 9                                        # discard port: refused on loopback
        runner = None
        if handler is not None:
            app = web.Application()
            app.router.add_route("*", "/{tail:.*}", handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
        async with aiohttp.ClientSession() as http:
            titular = inworld.TTS(api_key="x", base_url=f"http://127.0.0.1:{port}/", ws_url=f"ws://127.0.0.1:{port}/",
                                  http_session=http)
            voice = T._with_failover([("inworld", titular), ("openai", _StandIn())])
            t0 = time.perf_counter()
            async with voice.stream() as s:
                s.push_text("Hola, sigo aquí. ")
                s.end_input()
                async for ev in s:
                    out["stand_in_audio"] += ev.frame.data.tobytes().count(_B)
            out["s"] = time.perf_counter() - t0
            await voice.aclose()                         # cancels the probe of the hung titular
        if runner is not None:
            try:
                await asyncio.wait_for(runner.cleanup(), 2)
            except asyncio.TimeoutError:                 # a handler that hangs on purpose
                pass
    asyncio.run(asyncio.wait_for(run(), 15))
    return out


@pytest.mark.parametrize("case", ["refused", "handshake_402"])
def test_the_real_plugins_refusal_is_named_in_the_switch(world, case):
    """A refused socket or a 402 at the WebSocket upgrade comes up from aiohttp raw, with no `error` event: before,
    the alert said «no error reported» for exactly the failures that motivate the relay."""
    from aiohttp import web
    said, _ = world

    async def pay(_req):
        return web.Response(status=402, text="payment required")
    _real_inworld_against(None if case == "refused" else pay)
    causes = _alerts(said)
    assert causes and "no error reported" not in causes[0], said
    assert ("402" in causes[0]) if case == "handshake_402" else ("onnect" in causes[0]), causes


# ── a titular that HANGS (P1-4) ───────────────────────────────────────────────────────────────────────────────────
def _bound(monkeypatch, **kw):
    from voice.engine.speech import relay_bound
    pol = {**relay_bound._DEFAULTS, **kw}
    monkeypatch.setattr(relay_bound, "policy", lambda: pol)
    return relay_bound


async def _mute_ws(req):
    from aiohttp import web
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    async for _ in ws:                                   # accepts every message, answers none
        pass
    return ws


async def _hung_upgrade(_req):
    await asyncio.sleep(3600)


@pytest.mark.parametrize("handler,clock", [(_mute_ws, "no first audio"), (_hung_upgrade, "no sentence sent")])
def test_an_armed_bound_switches_a_hung_titular_once_without_a_retry(world, monkeypatch, handler, clock):
    """The REAL plugin against a socket that accepts and stays mute (measured before: 140 s, two 70 s attempts on the
    same socket) and against an upgrade that never answers (up to the HTTP client's 300 s)."""
    said, _ = world
    _bound(monkeypatch, mode="armed", tts_first_byte_s=0.4, tts_ready_s=0.4)
    out = _real_inworld_against(handler)
    causes = _alerts(said)
    assert out["stand_in_audio"] > 0 and out["s"] < 3.0, out
    assert causes and clock in causes[0] and "APITimeoutError" in causes[0], causes


def _slow_titular(delay: float) -> list:
    class _Slow(lk_tts.SynthesizeStream):
        async def _run(self, out) -> None:
            out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm", stream=True)
            out.start_segment(segment_id="s")
            async for d in self._input_ch:
                if isinstance(d, str) and d.strip():
                    self._mark_started()
                    await asyncio.sleep(delay)
                    out.push(_T * (RATE // 10))
                    out.flush()
            out.end_segment()

    class _SlowVoice(_ScriptedVoice):
        def stream(self, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
            return _Slow(tts=self, conn_options=conn_options)
    return _SlowVoice([])


@pytest.mark.parametrize("delay,says", [(0.6, True), (0.05, False)])
def test_in_shadow_a_late_titular_is_said_and_still_speaks(world, monkeypatch, delay, says):
    said, _ = world
    _bound(monkeypatch, mode="shadow", tts_first_byte_s=0.3, tts_ready_s=5.0)
    voice = T._with_failover([("inworld", _slow_titular(delay)), ("openai", _StandIn())])

    async def speak() -> int:
        got = 0
        async with voice.stream() as s:
            s.push_text("Una frase entera. ")
            s.end_input()
            async for ev in s:
                got += ev.frame.data.tobytes().count(_T)
        return got
    assert asyncio.run(asyncio.wait_for(speak(), 10)) > 0, "the titular still speaks in shadow"
    would = [e for e in EMITTED if e[0] == "provider" and e[2].get("extra", {}).get("would_switch")]
    assert bool(would) is says and not _alerts(said), (would, said)
    if says:
        assert "no first audio 0.3 s" in would[0][1]


def test_in_shadow_an_ear_that_never_answers_two_spans_is_said(world, monkeypatch):
    import time
    rb = _bound(monkeypatch, stt_span_s=0.01, stt_answer_s=0.02, stt_strikes=2)
    monkeypatch.setattr(rb, "_EAR", {"start": 0.0, "heard_at": 0.0, "strikes": 0, "pending": []})

    def span(heard: bool) -> None:
        rb.ear_state("speaking")
        time.sleep(0.02)
        if heard:
            rb.ear_heard()
        rb.ear_state("listening")
        time.sleep(0.04)

    def would() -> list:
        return [e for e in EMITTED if e[0] == "provider" and e[2].get("extra", {}).get("cat") == "stt"]
    span(True), span(False), span(True), span(False)
    rb.ear_state("speaking")
    assert not would(), "a word between two silent spans resets the count"
    span(False), span(False)
    rb.ear_state("speaking")
    assert len(would()) == 1 and "2 speech spans" in would()[0][1]

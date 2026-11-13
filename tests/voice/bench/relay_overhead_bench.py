"""What the voice relay costs when it is NOT used (V2-896): the titular healthy, the stand-in idle.

    ./.venv/bin/python -m tests.voice.bench.relay_overhead_bench [--runs 30]

Voice: the same streaming double (Inworld's shape: PCM, one flush after every chunk, two sentences 0.5 s apart) is read
direct, through LiveKit's stock `FallbackAdapter`, and through the engine's own (`tts._with_failover`). Reported: time to
first audio, and when the LAST sample of sentence one reached the session (a held tail shows here, not in the TTFB).
Ear: the delay between a streaming double emitting an interim and the session reading it, direct vs `stt.build_stt()`.
Doubles only — no network — so the numbers are the relay's own, not a provider's. Measured 2026-11-13 (30 runs):
sentence-one end p50 62 ms direct, 533 ms stock, 62 ms ours; TTFB p50 6.5 / 6.8 / 7.0 ms; ear +0.09 ms p50.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import statistics
import time

from livekit import rtc
from livekit.agents import stt as lk_stt, tts as lk_tts

RATE, CHUNK = 24000, 960          # 20 ms of 16-bit mono at 24 kHz


class _Sentences(lk_tts.SynthesizeStream):
    async def _run(self, out) -> None:
        out.initialize(request_id="r", sample_rate=RATE, num_channels=1, mime_type="audio/pcm", stream=True)
        out.start_segment(segment_id="s")
        async for d in self._input_ch:
            if isinstance(d, str) and d.strip():
                for _ in range(10):
                    await asyncio.sleep(0.005)
                    out.push(b"\x01\x00" * (CHUNK // 2))
                    out.flush()
        out.end_segment()


class _Voice(lk_tts.TTS):
    def __init__(self):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=True), sample_rate=RATE, num_channels=1)

    def synthesize(self, text, **kw):
        raise NotImplementedError

    def stream(self, *, conn_options=lk_tts.tts.DEFAULT_API_CONNECT_OPTIONS):
        return _Sentences(tts=self, conn_options=conn_options)


async def _speak(tts) -> tuple[float, float]:
    t0, marks, got = time.perf_counter(), [], 0
    async with tts.stream() as s:
        async def drive() -> None:
            s.push_text("Sentence one. ")
            await asyncio.sleep(0.5)
            s.push_text("Sentence two. ")
            s.end_input()
        task = asyncio.create_task(drive())
        async for ev in s:
            raw = ev.frame.data.tobytes()
            got += sum(1 for i in range(0, len(raw), 2) if raw[i] == 1)
            if got:
                marks.append((got, time.perf_counter() - t0))
        await task
    return marks[0][1], next(t for n, t in marks if n >= 10 * CHUNK // 2)


class _Interim(lk_stt.RecognizeStream):
    async def _run(self) -> None:
        async for it in self._input_ch:
            if isinstance(it, rtc.AudioFrame):
                self._event_ch.send_nowait(lk_stt.SpeechEvent(type=lk_stt.SpeechEventType.INTERIM_TRANSCRIPT,
                                           alternatives=[lk_stt.SpeechData(language="en", text=str(time.perf_counter()))]))


class _Ear(lk_stt.STT):
    def __init__(self):
        super().__init__(capabilities=lk_stt.STTCapabilities(streaming=True, interim_results=True))

    async def _recognize_impl(self, buffer, **kw):
        raise NotImplementedError

    def stream(self, *, language=None, conn_options=lk_stt.stt.DEFAULT_API_CONNECT_OPTIONS):
        return _Interim(stt=self, conn_options=conn_options, sample_rate=16000)


async def _listen(ear) -> list[float]:
    frame = rtc.AudioFrame(data=b"\0\0" * 160, sample_rate=16000, num_channels=1, samples_per_channel=160)
    lags: list[float] = []
    async with ear.stream() as s:
        async def feed() -> None:
            for _ in range(50):
                s.push_frame(frame)
                await asyncio.sleep(0.01)
            s.end_input()
        task = asyncio.create_task(feed())
        async for ev in s:
            if ev.type == lk_stt.SpeechEventType.INTERIM_TRANSCRIPT:
                lags.append(time.perf_counter() - float(ev.alternatives[0].text))
        await task
    return lags


def _p(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] * 1000


async def main(runs: int) -> None:
    from livekit.agents.tts import FallbackAdapter

    from config import models
    from voice.engine.speech import stt as S, tts as T
    rows: dict[str, list] = {"direct": [], "stock adapter": [], "engine adapter": []}
    for _ in range(runs):
        rows["direct"].append(await _speak(_Voice()))
        rows["stock adapter"].append(await _speak(FallbackAdapter([_Voice(), _Voice()], max_retry_per_tts=1)))
        rows["engine adapter"].append(await _speak(T._with_failover([("inworld", _Voice()), ("openai", _Voice())])))
    for name, v in rows.items():
        print(f"voice {name:15s} first audio p50 {_p([x[0] for x in v], .5):6.2f} ms · sentence-one end p50 "
              f"{_p([x[1] for x in v], .5):7.2f} ms, max {_p([x[1] for x in v], 1):7.2f} ms")
    S.registry._builders["deepgram"] = lambda vad=None: _Ear()
    S.registry._builders["openai"] = lambda vad=None: _Ear()
    S.SETTINGS = dataclasses.replace(S.SETTINGS, stt_provider="deepgram")
    models.failover = lambda name: {"provider": "openai"}
    direct, relayed = [], []
    for _ in range(max(3, runs // 3)):
        direct += await _listen(_Ear())
        relayed += await _listen(S.build_stt(vad=None))
    for name, v in (("direct", direct), ("engine adapter", relayed)):
        print(f"ear   {name:15s} event lag p50 {_p(v, .5):.3f} ms · p95 {_p(v, .95):.3f} ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=30)
    asyncio.run(main(ap.parse_args().runs))

"""Does agent-side voice isolation help STT without hurting clean speech? A measurement, not a test (V2-812 T-08).

Builds a synthetic, non-personal fixture — four utterances (2 Spanish, 2 English, OpenAI TTS) mixed with synthetic
road noise at 10/5/0 dB SNR and with a second competing voice at 6/0 dB SIR — publishes it into a LiveKit room and
records it back through `AudioStream`s with no filter, `NC()` and `BVC()`; also runs the WebRTC APM (noise
suppression + gain control + high-pass, the browser's «full» capture profile) offline. Every variant is transcribed
with Deepgram nova-3 and scored by word error rate against the script.

Needs OPENAI_API_KEY and DEEPGRAM_API_KEY, and a LiveKit project in LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET.
Against a self-hosted livekit-server the filters are refused by the plugin («not authorized for this connection»)
and pass audio through unchanged — the NC/BVC columns then equal «none» and say nothing about the filter.

    ./.venv/bin/python tests/voice/bench/voice_isolation_bench.py [--out DIR]

Decision rule for `ZAELAR_VOICE_ISOLATION`'s default: a variant ships ON only if it lowers WER under noise AND does
not raise it on the clean rows.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import tempfile
import unicodedata
import wave

import httpx
import numpy as np
from dotenv import load_dotenv
from scipy.signal import correlate, resample_poly

SR_TTS, SR = 24000, 48000
TARGET = [
    ("es", "Pon la música de la lista de conducción y baja un poco el volumen, por favor."),
    ("es", "Recuérdame mañana a las nueve llamar al taller para revisar los frenos."),
    ("en", "Play the driving playlist and turn the volume down a little, please."),
    ("en", "Remind me tomorrow at nine to call the garage about the brakes."),
]
OTHER = {
    "es": "¿Has visto el partido de anoche? El segundo tiempo fue increíble, de verdad, no me lo esperaba.",
    "en": "Did you see the game last night? The second half was amazing, honestly, I did not expect it.",
}
CONDITIONS = [("clean", None, None), ("road10", 10, None), ("road5", 5, None), ("road0", 0, None),
              ("voice6+road10", 10, 6), ("voice0+road10", 10, 0)]


def _tts(text: str, voice: str) -> np.ndarray:
    r = httpx.post("https://api.openai.com/v1/audio/speech", timeout=60,
                   headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                   json={"model": "tts-1", "voice": voice, "input": text, "response_format": "pcm"})
    r.raise_for_status()
    return np.frombuffer(r.content, dtype=np.int16).astype(np.float32) / 32768


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)) + 1e-12)


def _road(n: int, rng) -> np.ndarray:
    """Synthetic road noise: low-frequency rumble, engine harmonics, tyre hiss, a slow swell."""
    brown = np.cumsum(rng.standard_normal(n))
    brown -= np.convolve(brown, np.ones(2400) / 2400, mode="same")
    t = np.arange(n) / SR_TTS
    hum = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) / k for k, f in enumerate((38, 76, 114, 152), 1))
    hiss = np.convolve(rng.standard_normal(n), np.ones(6) / 6, mode="same")
    x = brown / np.std(brown) + 0.6 * hum / np.std(hum) + 0.4 * hiss / np.std(hiss)
    x *= 1 + 0.25 * np.sin(2 * np.pi * 0.3 * t)
    return x / np.std(x)


def build_fixture() -> tuple[np.ndarray, list[dict]]:
    rng = np.random.default_rng(812)
    clean = [(lang, txt, _tts(txt, "alloy")) for lang, txt in TARGET]
    other = {lang: _tts(t, "onyx") for lang, t in OTHER.items()}
    gap = np.zeros(int(1.5 * SR_TTS), np.float32)
    parts, clips, pos = [np.zeros(2 * SR_TTS, np.float32)], [], 2 * SR_TTS
    for cond, snr, sir in CONDITIONS:
        for lang, txt, s in clean:
            s = s / _rms(s) * 0.08
            mix = s.copy()
            if snr is not None:
                mix += _road(len(s), rng) * _rms(s) / 10 ** (snr / 20)
            if sir is not None:
                o = np.resize(other[lang], len(s))
                mix += o / _rms(o) * _rms(s) / 10 ** (sir / 20)
            clips.append({"cond": cond, "lang": lang, "ref": txt, "start": pos * 2, "len": len(mix) * 2})
            parts += [np.clip(mix, -1, 1).astype(np.float32), gap]
            pos += len(mix) + len(gap)
    return resample_poly(np.concatenate(parts), 2, 1).astype(np.float32), clips


async def room_pass(x: np.ndarray) -> dict[str, np.ndarray]:
    """Publish `x` and record it back unfiltered, through NC() and through BVC()."""
    from livekit import api, rtc
    from livekit.plugins import noise_cancellation as nc

    room = "vi-bench-" + os.urandom(3).hex()

    def token(identity: str) -> str:
        return (api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
                .with_identity(identity).with_grants(api.VideoGrants(room_join=True, room=room)).to_jwt())

    pub, sub = rtc.Room(), rtc.Room()
    ready, streams = asyncio.Event(), {}
    bufs: dict[str, list] = {"none": [], "nc": [], "bvc": []}

    @sub.on("track_subscribed")
    def _on(track, *_):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            for k, f in (("none", None), ("nc", nc.NC()), ("bvc", nc.BVC())):
                streams[k] = rtc.AudioStream.from_track(track=track, sample_rate=SR, num_channels=1,
                                                        noise_cancellation=f)
            ready.set()

    url = os.environ["LIVEKIT_URL"]
    await sub.connect(url, token("listener"))
    await pub.connect(url, token("speaker"))
    src = rtc.AudioSource(SR, 1)
    track = rtc.LocalAudioTrack.create_audio_track("mic", src)
    await pub.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    await asyncio.wait_for(ready.wait(), 20)

    async def drain(k: str):
        async for ev in streams[k]:
            bufs[k].append(np.frombuffer(ev.frame.data, np.int16).astype(np.float32) / 32768)

    tasks = [asyncio.create_task(drain(k)) for k in streams]
    await asyncio.sleep(1.0)
    pcm, step = (x * 32767).astype(np.int16), SR // 100
    for i in range(0, len(pcm) - step, step):
        await src.capture_frame(rtc.AudioFrame(pcm[i:i + step].tobytes(), SR, 1, step))
    await src.wait_for_playout()
    await asyncio.sleep(2.0)
    for t in tasks:
        t.cancel()
    await pub.disconnect()
    await sub.disconnect()
    return {k: _align(x, np.concatenate(b)) for k, b in bufs.items() if b}


def _align(ref: np.ndarray, y: np.ndarray) -> np.ndarray:
    lag = int(np.argmax(correlate(y[: SR * 25], ref[: SR * 20], mode="valid", method="fft")))
    return y[lag:]


def webrtc_full(x: np.ndarray) -> np.ndarray:
    from livekit import rtc
    apm = rtc.AudioProcessingModule(noise_suppression=True, auto_gain_control=True, high_pass_filter=True)
    y, out, n = (np.clip(x, -1, 1) * 32767).astype(np.int16), [], SR // 100
    for i in range(0, len(y) - n + 1, n):
        f = rtc.AudioFrame(y[i:i + n].tobytes(), SR, 1, n)
        apm.process_stream(f)
        out.append(np.frombuffer(f.data, np.int16).astype(np.float32) / 32768)
    return np.concatenate(out)


_NUM = {"nueve": "9", "nine": "9"}


def _words(s: str) -> list[str]:
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return [_NUM.get(w, w) for w in re.sub(r"[^a-z0-9 ]+", " ", s).split()]


def wer(ref: str, hyp: str) -> float:
    r, h = _words(ref), _words(hyp)
    d = np.arange(len(h) + 1)
    for i, rw in enumerate(r, 1):
        prev, d[0] = d.copy(), i
        for j, hw in enumerate(h, 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (rw != hw))
    return d[len(h)] / max(1, len(r))


def transcribe(seg: np.ndarray, lang: str) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes())
    r = httpx.post(f"https://api.deepgram.com/v1/listen?model=nova-3&language={lang}", timeout=60,
                   headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}",
                            "Content-Type": "audio/wav"}, content=buf.getvalue())
    r.raise_for_status()
    return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=tempfile.mkdtemp(prefix="vi-bench-"))
    ap.add_argument("--no-room", action="store_true", help="skip the LiveKit pass (WebRTC APM only)")
    a = ap.parse_args()
    load_dotenv()
    x, clips = build_fixture()
    variants = {"none": x, "webrtc_full": webrtc_full(x)}
    if not a.no_room:
        variants.update({k: v for k, v in asyncio.run(room_pass(x)).items() if k != "none"})
    scores: dict[tuple[str, str], list[float]] = {}
    for v, y in variants.items():
        for c in clips:
            seg = y[max(0, c["start"] - SR // 4): c["start"] + c["len"] + SR // 4]
            scores.setdefault((c["cond"], v), []).append(wer(c["ref"], transcribe(seg, c["lang"])))
    print("WER, mean of 4 utterances (2 es + 2 en), Deepgram nova-3")
    print("condition".ljust(16) + "".join(v.rjust(13) for v in variants))
    for cond, *_ in CONDITIONS:
        print(cond.ljust(16) + "".join(f"{np.mean(scores[(cond, v)]):13.3f}" for v in variants))


if __name__ == "__main__":
    main()

"""Synthetic utterances for the audio scenarios, from the engine's own TTS providers, cached on disk.

A voice is `provider:name`. Inworld gives per-word timestamps (`timestampType: WORD`), so its utterances carry exact
word truth; OpenAI and macOS `say` give the utterance's span only. Keys are read from the credential store into
memory and never printed or written. Every synthesis is cached by (voice, text): a scenario costs money once.

The audio is returned as 16 kHz mono float32 in [-1, 1]; nothing is played.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 16_000
ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "tests" / "runs" / "conversation" / "audio" / "voices"

#: The speakers. Three voices per language for the person (different provider, timbre and pace), one reserved for
#: «the other person» and one for «the TV» (plan §5.2). The mixed-language person is ONE multilingual voice that
#: says both languages, as a person who switches does. Voice ids come from the engine's own catalogs
#: (`voice/engine/speech/*_voices.py`).
SPEAKERS: dict[str, str] = {
    "es_1": "inworld:Alvaro", "es_2": "inworld:Marta", "es_3": "elevenlabs:LlZr3QuzbW4WrPjgATHG",
    "en_1": "inworld:Reed", "en_2": "inworld:Ashley", "en_3": "cartesia:47c38ca4-5f35-497b-b1a3-415245fb35e1|en",
    "mix_1": "elevenlabs:EXAVITQu4vr4xnSDxMaL", "mix_2": "elevenlabs:LlZr3QuzbW4WrPjgATHG",
    "mix_3": "elevenlabs:cjVigY5qzO86Huf0OWal",
    "es_other": "inworld:Sergio", "en_other": "inworld:Freddie",
    "es_tv": "openai:onyx", "en_tv": "openai:nova",
    "es_agent": "inworld:Alvaro", "en_agent": "inworld:Reed",    # the engine's pinned voices: our own echo
    # the five hand-written scenarios' names
    "es_a": "inworld:Alvaro", "es_b": "inworld:Marta", "en_a": "inworld:Reed", "en_b": "inworld:Ashley",
}
USER_VOICES = {"es": ("es_1", "es_2", "es_3"), "en": ("en_1", "en_2", "en_3"), "mix": ("mix_1", "mix_2", "mix_3")}
#: The person's voices that give word times (Cartesia does not as called here): the pause cells' voices.
TIMED_USER_VOICES = {"es": ("es_1", "es_2", "es_3"), "en": ("en_1", "en_2"), "mix": ("mix_1", "mix_2", "mix_3")}


@dataclass(frozen=True)
class Utterance:
    voice: str
    text: str
    audio: np.ndarray                                   # float32, RATE, mono
    words: tuple[tuple[str, float, float], ...]          # (word, start_s, end_s) within the utterance; () if unknown

    @property
    def seconds(self) -> float:
        return len(self.audio) / RATE


def _store_key(name: str) -> str:
    """A key from the env or the engine's credential store, in memory only."""
    if os.environ.get(name):
        return os.environ[name]
    from tests.platform.sandbox_engine import OPERATOR_STORE
    if OPERATOR_STORE.is_file():
        for line in OPERATOR_STORE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return ""


def _resample(x: np.ndarray, src: int) -> np.ndarray:
    if src == RATE:
        return x.astype(np.float32)
    from scipy.signal import resample_poly
    g = np.gcd(src, RATE)
    return resample_poly(x, RATE // g, src // g).astype(np.float32)


def _pcm16(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0


def _wav_bytes(blob: bytes) -> tuple[np.ndarray, int]:
    with tempfile.NamedTemporaryFile(suffix=".wav") as fh:
        fh.write(blob)
        fh.flush()
        with wave.open(fh.name, "rb") as w:
            rate, ch = w.getframerate(), w.getnchannels()
            x = _pcm16(w.readframes(w.getnframes()))
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def _inworld(name: str, text: str) -> tuple[np.ndarray, tuple]:
    import urllib.request
    key = _store_key("INWORLD_API_KEY")
    if not key:
        raise RuntimeError("no INWORLD_API_KEY")
    body = {"text": text, "voiceId": name, "modelId": "inworld-tts-2", "timestampType": "WORD",
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": RATE}}
    req = urllib.request.Request("https://api.inworld.ai/tts/v1/voice", json.dumps(body).encode(),
                                 {"Authorization": f"Basic {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        data = json.load(fh)
    blob = base64.b64decode(data["audioContent"])
    x, rate = _wav_bytes(blob) if blob[:4] == b"RIFF" else (_pcm16(blob), RATE)
    align = (data.get("timestampInfo") or {}).get("wordAlignment") or {}
    words = tuple(zip(align.get("words") or [], align.get("wordStartTimeSeconds") or [],
                      align.get("wordEndTimeSeconds") or []))
    return _resample(x, rate), words


def _openai(name: str, text: str) -> tuple[np.ndarray, tuple]:
    import urllib.request
    key = _store_key("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    body = {"model": "gpt-4o-mini-tts", "voice": name, "input": text, "response_format": "wav"}
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        blob = fh.read()
    x, rate = _wav_bytes(blob)
    return _resample(x, rate), ()


def _elevenlabs(name: str, text: str) -> tuple[np.ndarray, tuple]:
    """`name` = an ElevenLabs voice id from `voice/engine/speech/elevenlabs_voices.py`; multilingual model."""
    import urllib.request
    key = _store_key("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("no ELEVENLABS_API_KEY")
    body = {"text": text, "model_id": "eleven_multilingual_v2"}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{name}?output_format=pcm_16000",
                                 json.dumps(body).encode(), {"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return _pcm16(fh.read()), ()


def _elevenlabs_timed(name: str, text: str) -> tuple[np.ndarray, tuple]:
    """ElevenLabs with its character alignment (`/with-timestamps`), grouped into words: start of the first
    character, end of the last."""
    import urllib.request
    key = _store_key("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("no ELEVENLABS_API_KEY")
    body = {"text": text, "model_id": "eleven_multilingual_v2"}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{name}/with-timestamps"
                                 f"?output_format=pcm_16000", json.dumps(body).encode(),
                                 {"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        data = json.load(fh)
    al = data.get("alignment") or {}
    words, cur, t0, t1 = [], "", None, None
    for ch, a, b in zip(al.get("characters") or [], al.get("character_start_times_seconds") or [],
                        al.get("character_end_times_seconds") or []):
        if ch.isspace():
            if cur:
                words.append((cur, t0, t1))
            cur, t0, t1 = "", None, None
            continue
        cur, t0, t1 = cur + ch, (a if t0 is None else t0), b
    if cur:
        words.append((cur, t0, t1))
    return _pcm16(base64.b64decode(data["audio_base64"])), tuple(words)


def _cartesia(name: str, text: str) -> tuple[np.ndarray, tuple]:
    """`name` = a Cartesia voice id from `voice/engine/speech/cartesia_voices.py`."""
    import urllib.request
    key = _store_key("CARTESIA_API_KEY")
    if not key:
        raise RuntimeError("no CARTESIA_API_KEY")
    lang = "es" if "|es" in name else "en"
    vid = name.split("|")[0]
    body = {"model_id": "sonic-2", "transcript": text, "voice": {"mode": "id", "id": vid}, "language": lang,
            "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": RATE}}
    req = urllib.request.Request("https://api.cartesia.ai/tts/bytes", json.dumps(body).encode(),
                                 {"X-API-Key": key, "Cartesia-Version": "2024-11-13",
                                  "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return _pcm16(fh.read()), ()


def _say(name: str, text: str) -> tuple[np.ndarray, tuple]:
    """macOS `say` to a FILE (`-o`): nothing reaches the speakers."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "u.wav"
        subprocess.run(["say", "-v", name, "-o", str(out), "--data-format=LEI16@16000", text], check=True,
                       capture_output=True)
        with wave.open(str(out), "rb") as w:
            rate = w.getframerate()
            x = _pcm16(w.readframes(w.getnframes()))
    return _resample(x, rate), ()


_PROVIDERS = {"inworld": _inworld, "openai": _openai, "elevenlabs": _elevenlabs, "cartesia": _cartesia, "say": _say,
              "elevenlabs_ts": _elevenlabs_timed}
#: The voices that give per-word times, as `provider:name` → the provider call that returns them (plan §5.2: a pause
#: is inserted at a word boundary of ONE utterance, so only these voices speak in the pause cells).
TIMED = {"inworld": "inworld", "elevenlabs": "elevenlabs_ts"}


def timed(speaker_or_voice: str) -> str:
    """The same voice through its timed call, or '' when its provider gives no word times."""
    voice = SPEAKERS.get(speaker_or_voice, speaker_or_voice)
    provider, _, name = voice.partition(":")
    return f"{TIMED[provider]}:{name}" if provider in TIMED else ""


def _trim(x: np.ndarray, words: tuple) -> tuple[np.ndarray, tuple]:
    """Cut the TTS's leading and trailing silence, so the scenario decides every pause; word times move with it."""
    level = np.abs(x)
    idx = np.flatnonzero(level > 0.01)
    if not len(idx):
        return x, words
    a, b = max(0, idx[0] - RATE // 100), min(len(x), idx[-1] + RATE // 50)
    shift = a / RATE
    words = tuple((w, max(0.0, s - shift), max(0.0, e - shift)) for w, s, e in words)
    return x[a:b], words


def _clean(words) -> tuple[tuple[str, float, float], ...]:
    """Word tokens only: the aligner also times spaces and punctuation, which no ear will ever hear as a word."""
    out = []
    for w, s, e in words:
        token = "".join(ch for ch in str(w) if ch.isalnum() or ch in "'-")
        if token:
            out.append((token, round(float(s), 3), round(float(e), 3)))
    return tuple(out)


def utter(speaker_or_voice: str, text: str) -> Utterance:
    """One utterance, from the cache or synthesised once. `speaker_or_voice`: a key of SPEAKERS or `provider:name`."""
    voice = SPEAKERS.get(speaker_or_voice, speaker_or_voice)
    provider, _, name = voice.partition(":")
    h = hashlib.sha1(f"{voice}\n{text}".encode()).hexdigest()[:16]
    wav, meta = CACHE / f"{h}.wav", CACHE / f"{h}.json"
    if wav.is_file() and meta.is_file():
        with wave.open(str(wav), "rb") as w:
            x = _pcm16(w.readframes(w.getnframes()))
        words = _clean(json.loads(meta.read_text(encoding="utf-8"))["words"])
        return Utterance(voice, text, x, words)
    x, words = _PROVIDERS[provider](name, text)
    x, words = _trim(x, _clean(words))
    CACHE.mkdir(parents=True, exist_ok=True)
    write_wav(wav, x)
    meta.write_text(json.dumps({"voice": voice, "text": text, "words": words}, ensure_ascii=False), encoding="utf-8")
    return Utterance(voice, text, x, words)


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())

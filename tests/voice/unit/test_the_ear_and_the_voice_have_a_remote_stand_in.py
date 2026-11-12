"""V2-889 row 10 — the ear and the voice each have a REMOTE stand-in, so a provider outage never leaves the agent
deaf or mute where no local model can run (a cloud container).

Before: the `stt` row named a failover nobody read (an outage of the titular ear = a deaf agent), and the `tts` row's
stand-in was Kokoro, which refuses to build in a container (the voice went mute on the titular's first outage). Now
both rows point at OpenAI (operator, 2026-11-12: «OpenAI sí tenemos crédito, siempre»), LiveKit's `FallbackAdapter`
switches, every switch is an alert, the session keeps reading the TITULAR's capabilities, and the stand-in voice keeps
the gender he chose.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from livekit.agents import stt as lk_stt

from voice.engine.speech import stt as S

ENGINE = Path(__file__).resolve().parents[3]


class _Ear(lk_stt.STT):
    def __init__(self, name, *, streaming=True, interim=True, aligned="word"):
        super().__init__(capabilities=lk_stt.STTCapabilities(streaming=streaming, interim_results=interim,
                                                             aligned_transcript=aligned if streaming else False))
        self.name = name

    async def _recognize_impl(self, buffer, **kw):  # pragma: no cover — never called here
        raise NotImplementedError


class _Vad:
    """The adapter only stores it for the non-streaming stand-in's StreamAdapter."""
    capabilities = type("C", (), {"update_interval": 0.032})()

    def on(self, *a, **k):
        return None


@pytest.fixture
def ears(monkeypatch):
    builders = dict(S.registry._builders)
    monkeypatch.setattr(S.registry, "_builders", builders)
    monkeypatch.setattr(S, "SETTINGS", dataclasses.replace(S.SETTINGS, stt_provider="deepgram"))
    from config import models
    monkeypatch.setattr(models, "failover", lambda name: {"provider": "openai"} if name == "stt" else None)
    said: list = []
    monkeypatch.setattr(S, "_note", lambda msg, **extra: said.append((msg, extra)))
    return builders, said


def test_both_rows_name_a_remote_stand_in_that_is_registered():
    rows = json.loads((ENGINE / "config" / "models.default.json").read_text(encoding="utf-8"))
    rows = rows.get("services", rows)
    from voice.engine.speech import tts as T
    assert rows["stt"]["failover"]["provider"] == "openai" and "openai" in S.registry.names()
    assert rows["tts"]["failover"]["provider"] == "openai" and "openai" in T.registry.names()


def test_the_ear_fails_over_and_keeps_the_titulars_capabilities(ears):
    builders, said = ears
    a, b = _Ear("deepgram"), _Ear("openai", streaming=False, interim=False)
    builders["deepgram"] = lambda vad=None: a
    builders["openai"] = lambda vad=None: b
    built = S.build_stt(vad=_Vad())
    assert isinstance(built, lk_stt.FallbackAdapter) and built._zaelar_providers == ["deepgram", "openai"]
    assert built.capabilities.interim_results and built.capabilities.aligned_transcript == "word", \
        "the session must read the titular's capabilities, not the intersection"
    from livekit.agents.stt.fallback_adapter import AvailabilityChangedEvent
    built.emit("stt_availability_changed", AvailabilityChangedEvent(stt=a, available=False))
    assert said and said[-1][1].get("stand_in") == "openai", "a switch is said, never silent"


def test_an_ear_whose_stand_in_cannot_be_built_says_so_and_hears_alone(ears):
    builders, said = ears
    a = _Ear("deepgram")
    builders["deepgram"] = lambda vad=None: a

    def _no_key(vad=None):
        raise ValueError("OpenAI STT: no OPENAI_API_KEY")
    builders["openai"] = _no_key
    assert S.build_stt(vad=_Vad()) is a
    assert said and said[-1][1].get("standin_missing")


def test_the_stand_in_voice_keeps_his_gender(monkeypatch):
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "voices_for", lambda p=None, lang=None: [{"voice": "m1", "gender": "m"},
                                                                     {"voice": "f1", "gender": "f"}])
    monkeypatch.setattr(V, "_picked_voice", lambda: "m1")
    assert V.default_voice_for("openai") == "ash"
    monkeypatch.setattr(V, "_picked_voice", lambda: "f1")
    assert V.default_voice_for("openai") == "coral"

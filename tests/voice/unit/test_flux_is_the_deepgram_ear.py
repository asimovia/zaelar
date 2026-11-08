"""Deepgram Flux is the default ear, nova-3 the alternative by env, and egress carries Flux's own family (V2-863).

Measured before the change (12 real sessions, 2026-11-08): the end-of-turn hold by silence (`voice/endpointing.py`)
alone was 1.9 s p50 / 2.6 s p90 of every turn. Flux's own end-of-turn model closes the turn ~260 ms after the last
word and announces an EAGER end of turn before confirming it. With it, the session reads the end of turn from the
STT (`turn_detection="stt"`). The v2 socket lives on `/v2`, so egress needs a family of its own for it — a mediated
deployment that routed Flux to the v1 base would open a socket to nothing.
"""
from __future__ import annotations

import dataclasses

import pytest
from livekit.plugins import deepgram as lk_deepgram

from nucleo.energy import egress
from voice.engine.speech.stt import deepgram as dg


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    # `build()` constructs the plugin, which refuses to exist without a key and never dials out here.
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-placeholder")
    monkeypatch.setattr(dg, "SETTINGS", dataclasses.replace(dg.SETTINGS, deepgram_api_key="test-placeholder",
                                                            stt_provider="deepgram"))
    monkeypatch.setattr(dg.langs, "first_run_auto", lambda: False)
    yield


def _with(**changes):
    return dataclasses.replace(dg.SETTINGS, **changes)


def test_the_default_deepgram_ear_is_flux_general_multi(monkeypatch):
    stt = dg.build()
    assert isinstance(stt, lk_deepgram.STTv2)
    assert stt._opts.model == "flux-general-multi"
    assert stt._opts.eager_eot_threshold == 0.5
    assert stt._opts.eot_threshold == 0.7
    assert stt._opts.eot_timeout_ms == 3000
    assert stt._opts.endpoint_url.startswith("wss://") and stt._opts.endpoint_url.endswith("/v2/listen")


def test_flux_is_hinted_with_the_chosen_language_and_listens_to_everything_on_the_first_run(monkeypatch):
    assert dg.build()._opts.language_hint == [dg.langs.current_code()]
    monkeypatch.setattr(dg.langs, "first_run_auto", lambda: True)
    assert dg.build()._opts.language_hint == [], "no hint while `i18n.init.detect` still has to classify his first sentence"


def test_nova_3_by_env_is_the_previous_ear(monkeypatch):
    monkeypatch.setattr(dg, "SETTINGS", _with(stt_model_deepgram="nova-3"))
    stt = dg.build()
    assert isinstance(stt, lk_deepgram.STT) and not isinstance(stt, lk_deepgram.STTv2)
    assert not dg.flux_active()


@pytest.mark.parametrize("provider,model,active", [
    ("deepgram", "flux-general-multi", True),
    ("deepgram", "flux-general-en", True),
    ("deepgram", "nova-3", False),
    ("voxtral", "flux-general-multi", False),
    ("whisper_local", "flux-general-multi", False),
])
def test_flux_is_active_only_with_the_deepgram_provider_and_a_flux_model(monkeypatch, provider, model, active):
    monkeypatch.setattr(dg, "SETTINGS", _with(stt_provider=provider, stt_model_deepgram=model))
    assert dg.flux_active() is active


def test_egress_carries_flux_as_its_own_family_on_v2():
    assert egress.upstream_of("https://api.deepgram.com/v2/listen") == ("deepgram_flux", "https://api.deepgram.com/v2")
    assert egress.upstream_of("https://api.deepgram.com/v1/listen") == ("deepgram", "https://api.deepgram.com/v1")
    assert egress.base_of("deepgram_flux") == "https://api.deepgram.com/v2"

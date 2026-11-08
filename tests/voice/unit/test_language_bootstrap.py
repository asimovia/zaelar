"""
Product LANGUAGE bootstrap (2026-08-09). Two invariants that broke separately and together
determined whether zaelar could adapt to the installer's language:

1. **The default is ENGLISH.** A clean installation started with the UI in English (`store.lang()` falls back to "en")
   and the VOICE in Spanish (`langs.DEFAULT_LANG = "es"`) — inconsistent and contrary to the operator's norm.
2. **On the first run, STT transcribes in AUTO.** The autodetection in `i18n.init.detect` classifies the
   operator's FIRST phrase; if STT is already locked to a language, that phrase arrives transcribed by the
   wrong model and there is nothing to classify. `whisper_local` did this; the REMOTE backends (deepgram/voxtral) DID NOT — meaning
   autodetection could not work in the cloud profile, the production one. Each backend handles «auto» in
   its own way, which is why all three are checked separately: omitting the parameter in Deepgram is NOT auto (the
   server falls back to en-US).
"""
from __future__ import annotations

import pytest

from voice.engine.core import langs


def test_product_default_language_is_english():
    assert langs.DEFAULT_LANG == "en"


def test_first_run_auto_follows_the_detector(monkeypatch):
    from i18n.init import detect

    monkeypatch.setattr(detect, "should_detect", lambda: True)
    assert langs.first_run_auto() is True
    monkeypatch.setattr(detect, "should_detect", lambda: False)
    assert langs.first_run_auto() is False


def test_first_run_auto_is_fail_closed(monkeypatch):
    """If i18n crashes or is unavailable, STT behaves as usual (fixed language) — never the other way around."""
    from i18n.init import detect

    def boom():
        raise RuntimeError("i18n no disponible")

    monkeypatch.setattr(detect, "should_detect", boom)
    assert langs.first_run_auto() is False


def _captured_stt_kwargs(monkeypatch, module, plugin_attr, plugin_mod):
    seen = {}

    class _Fake:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(plugin_mod, plugin_attr, _Fake)
    module.build()
    return seen


@pytest.mark.parametrize("detecting, expected", [(True, "multi"), (False, "es")])
def test_deepgram_asks_for_multi_only_while_detecting(monkeypatch, detecting, expected):
    """nova-3 (`ZAELAR_STT_MODEL_DG=nova-3`): the v1 ear takes a `language`, and «multi» is its only auto."""
    import dataclasses

    from livekit.plugins import deepgram as _dg

    from voice.engine.speech.stt import deepgram as adapter

    monkeypatch.setattr(adapter, "SETTINGS", dataclasses.replace(adapter.SETTINGS, stt_model_deepgram="nova-3"))
    monkeypatch.setattr(langs, "first_run_auto", lambda: detecting)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    kw = _captured_stt_kwargs(monkeypatch, adapter, "STT", _dg)
    assert kw["language"] == expected


@pytest.mark.parametrize("detecting, expected", [(True, []), (False, ["es"])])
def test_flux_is_hinted_only_once_a_language_is_chosen(monkeypatch, detecting, expected):
    """Flux, the default ear (V2-863): `flux-general-multi` listens to every language and takes a HINT, never a
    lock — none on the first run, so `i18n.init.detect` classifies a clean first sentence."""
    from livekit.plugins import deepgram as _dg

    from voice.engine.speech.stt import deepgram as adapter

    monkeypatch.setattr(langs, "first_run_auto", lambda: detecting)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    kw = _captured_stt_kwargs(monkeypatch, adapter, "STTv2", _dg)
    assert kw.get("language_hint", []) == expected
    assert "language" not in kw


@pytest.mark.parametrize("detecting", [True, False])
def test_voxtral_omits_language_only_while_detecting(monkeypatch, detecting):
    from livekit.plugins import mistralai as _mi

    from voice.engine.speech.stt import voxtral as adapter

    monkeypatch.setattr(langs, "first_run_auto", lambda: detecting)
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    kw = _captured_stt_kwargs(monkeypatch, adapter, "STT", _mi)
    if detecting:
        assert "language" not in kw, "passing a language on the first run kills autodetection"
    else:
        assert kw["language"] == "es"


# 3. **Locking the language MOVES THE MEMORY TOO.** The third invariant, added 2026-08-14 after the operator
#    asked what a brand-new account actually starts from. `lock()` persisted the setting, built the UI bundle
#    and told the frontend to switch — and left `state.language` untouched. That field is what
#    `nucleo/mem_processor._render` reads to pick the language every pill is written in, so a French operator
#    got French speech, French STT and a French UI while their memory was distilled, forever, into the default.
#    The memory is deliberately MONOLINGUAL in the operator's language; that only holds if detection moves it.

def test_locking_the_language_also_moves_the_memory(monkeypatch):
    import asyncio
    from i18n.init import detect

    written = {}
    monkeypatch.setattr(detect, "_should_cache", None, raising=False)
    # Isolate the three side effects we are NOT testing here (settings file, bundle generation, SSE).
    import config.settings as cs
    monkeypatch.setattr(cs, "update", lambda d: None)
    import i18n.init as i18n_init

    async def _noop(code):
        return None

    monkeypatch.setattr(i18n_init, "prepare", _noop)
    from memory import api as memapi
    monkeypatch.setattr(memapi, "set_state", lambda fields: written.update(fields))

    res = asyncio.run(detect.lock("fr"))
    assert res["ok"] is True
    assert written.get("language") == "fr", (
        "detection moved the voice and the UI but not the memory: pills would keep being written in the "
        "previous language forever"
    )

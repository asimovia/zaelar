"""A language switch re-points EVERY voice of the failover TTS, each in its own provider (2026-10-04).

The operator, on a new cloud account: «me pone un británico hablando español». Since the failover row became a
mechanism (V2-778 F0-7, node 2.202) the session's TTS is LiveKit's `FallbackAdapter` over the titular and its
stand-in — and the adapter has no `update_options`. So `live_tts.apply_voice`, the seam V2-733 built to move the
LIVE voice when the language locks, found nothing to call and left both voices as the idle worker had built them:
English, before any language was chosen. The adapter's voices are re-pointed one by one now — the titular to the
voice the settings chose, the stand-in to its own provider's voice for that language (an Inworld name means
nothing to ElevenLabs).
"""
from __future__ import annotations


class _Fake:
    def __init__(self):
        self.calls = []

    def update_options(self, *, voice=None, language=None):
        self.calls.append((voice, language))


class _Adapter:
    """The shape `build_tts` hands the session: no update_options of its own, the instances inside."""
    def __init__(self, a, b):
        self._tts_instances = [a, b]
        self._zaelar_providers = ["inworld", "elevenlabs"]


def test_both_voices_of_the_adapter_follow_the_language(monkeypatch):
    from voice.engine.speech import live_tts, voices
    monkeypatch.setattr(voices, "selected_voice", lambda p=None: "")
    monkeypatch.setattr(voices, "default_voice_for", lambda p=None, lang=None, region=None:
                        {"inworld": "Alvaro", "elevenlabs": "es-voice-id"}.get(p, ""))
    a, b = _Fake(), _Fake()
    live_tts.attach(_Adapter(a, b), "inworld")
    try:
        assert live_tts.apply_voice("Alvaro", "es") is True
    finally:
        live_tts.detach()
    assert a.calls == [("Alvaro", "es")], a.calls
    assert b.calls == [("es-voice-id", "es")], "the stand-in kept the idle worker's English voice"


def test_the_real_adapter_built_by_the_engine_is_re_pointed(monkeypatch):
    import dataclasses
    from livekit.agents import tts as lk_tts
    from voice.engine.speech import tts as T, live_tts, voices
    from config import models

    class _Lk(lk_tts.TTS):
        def __init__(self):
            super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1)
            self.calls = []

        def update_options(self, *, voice=None, language=None):
            self.calls.append((voice, language))

        def synthesize(self, text, **kw):  # pragma: no cover
            raise NotImplementedError

    a, b = _Lk(), _Lk()
    builders = dict(T.registry._builders)
    builders.update({"inworld": lambda: a, "elevenlabs": lambda: b})
    monkeypatch.setattr(T.registry, "_builders", builders)
    monkeypatch.setattr(T, "SETTINGS", dataclasses.replace(T.SETTINGS, tts_provider="inworld"))
    monkeypatch.setattr(models, "failover", lambda name: {"provider": "elevenlabs"} if name == "tts" else None)
    monkeypatch.setattr(voices, "selected_voice", lambda p=None: "")
    monkeypatch.setattr(voices, "default_voice_for", lambda p=None, lang=None, region=None:
                        {"inworld": "Alvaro", "elevenlabs": "es-voice-id"}.get(p, ""))
    built = T.build_tts()
    assert isinstance(built, lk_tts.FallbackAdapter)
    live_tts.attach(built, "inworld")
    try:
        assert live_tts.apply_voice("Alvaro", "es") is True
    finally:
        live_tts.detach()
    assert a.calls == [("Alvaro", "es")] and b.calls == [("es-voice-id", "es")], (a.calls, b.calls)


def test_a_language_that_lands_in_the_voice_process_re_points_the_voice_already_speaking(monkeypatch):
    """The voice runs in its own process: the language he picks lives in the BODY's env and reaches this one with
    the body's next message (`apply_env`) — after the session's TTS was attached and pointed with the language
    this process knew then. Whatever message carries it, the live voices follow it, the stand-in included; a
    setting that says nothing about the voice moves nothing."""
    from voice.engine.pipeline import remote_brain
    from voice.engine.speech import live_tts, voices
    by_lang = {("inworld", "en"): "Reed", ("inworld", "es"): "Alvaro",
               ("elevenlabs", "en"): "en-voice-id", ("elevenlabs", "es"): "es-voice-id"}
    monkeypatch.setattr(voices, "selected_voice", lambda p=None: "")
    monkeypatch.setattr(voices, "default_voice_for", lambda p=None, lang=None, region=None:
                        by_lang.get((p, lang or voices.langs.current_code()), ""))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    a, b = _Fake(), _Fake()
    live_tts.attach(_Adapter(a, b), "inworld")
    try:
        live_tts.apply_current()                     # the session comes up before the language reached this process
        assert a.calls == [("Reed", "en")] and b.calls == [("en-voice-id", "en")]
        assert remote_brain.apply_env({"ZAELAR_SOME_MODE": "1"}) == 1
        assert len(a.calls) == 1, "a setting that is not the voice's re-pointed it"
        assert remote_brain.apply_env({"ZAELAR_LANGUAGE": "es"}) == 1
    finally:
        live_tts.detach()
        import os
        os.environ.pop("ZAELAR_SOME_MODE", None)
    assert a.calls[-1] == ("Alvaro", "es"), "the titular kept the voice of the language it was built in"
    assert b.calls[-1] == ("es-voice-id", "es"), "the stand-in kept the voice of the language it was built in"

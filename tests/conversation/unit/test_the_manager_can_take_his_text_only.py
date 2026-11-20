"""The manager can take his TEXT only (node 13.101, V2-941): `conversation_manager: "text"` (or
`ZAELAR_CONVERSATION=text`) sends the typed doors through the manager while every voice session stays on the old
path — its decision answers off, by the account, «text only», and that is a choice, not a refusal to alert. `true`
is both, `false` neither. The fail-closed checks hold for text as for voice.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.conversation_host import switch, voice_session


@pytest.fixture
def account(monkeypatch):
    from config import settings
    from nucleo.conversation_host import config
    monkeypatch.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.delenv(switch.ENV, raising=False)
    monkeypatch.setattr(config, "build", lambda: (None, []))
    value = {"v": None}
    real = settings.get
    monkeypatch.setattr(settings, "get", lambda key, default=None: value["v"] if key == switch.SETTING
                        else real(key, default))
    return value


@pytest.mark.parametrize("value, typed, voice", [("text", True, False), (True, True, True), (False, False, False)])
def test_text_only_sends_the_typed_doors_and_keeps_the_voice_old(account, value, typed, voice):
    account["v"] = value
    assert switch.decide(None).on is typed                                  # a text door (run_turn's)
    asked = voice_session.ask(None)                                         # what the voice process asks
    assert asked["on"] is voice
    if value == "text":
        assert (asked["by"], asked["why"]) == ("account", switch.TEXT_ONLY)
    from voice import observer
    alerts = []
    real = observer.emit
    observer.emit = lambda kind, label, **kw: alerts.append(label) if kind == "alert" else None
    try:
        legacy = SimpleNamespace()                                          # a voice session on the old path
        voice_session.started(legacy, {"conv": voice, "conv_by": asked["by"], "conv_why": asked["why"]})
    finally:
        observer.emit = real
    assert switch.typed_on(legacy) is typed and switch.on(legacy) is voice
    assert "conversation manager refused" not in alerts                     # text only is a choice, never a refusal


def test_the_environment_can_ask_for_text_only(account, monkeypatch):
    monkeypatch.setenv(switch.ENV, "text")
    assert switch.decide(None).on and not voice_session.ask(None)["on"]


def test_text_only_still_fails_closed(account, monkeypatch):
    account["v"] = "text"
    monkeypatch.delenv("ZAELAR_HOLD_OUTBOUND")
    assert not switch.decide(None).on


def test_a_typed_line_of_a_voice_session_on_the_old_path_goes_to_the_manager(account, monkeypatch):
    from nucleo.conversation_host import entry
    from voice.engine.pipeline import agent_events
    account["v"] = "text"
    handed, old = [], []
    monkeypatch.setattr(entry, "typed", lambda txt, dev="", **kw: handed.append(txt))
    monkeypatch.setattr(agent_events, "_route_typed", lambda txt, **kw: old.append(txt))
    legacy = SimpleNamespace()
    voice_session.started(legacy, {"conv": False, "conv_by": "account", "conv_why": switch.TEXT_ONLY})
    agent_events.receive_typed("w1", _emit=lambda *a, **k: None, session=legacy)
    assert handed == ["w1"] and old == []

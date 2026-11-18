"""The «a ver» send of 2026-11-17 (19:16), replayed at the turn's hand-off: the order is the message owner's (V2-938).

«A ver, …, ¿me vas a mandar un mensaje a Quinn diciéndole que estamos en batería?»: the show guard read the bare «ver»
and swapped the model's `send_to` for a show of the card. A message call is handed to its owner (`nucleo/send`)
before any ladder or guard reads it: the call does not run, no worker is commissioned, and its fields ride as a hint.
The people are invented.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

ORDER = "A ver, Johnny, vamos a hacer una cosa ahora. ¿Me vas a mandar un mensaje a Quinn diciéndole que estamos en batería?"
TEXT = "estamos en batería"


def _call(esc: dict, *, tag_emit=None, apply=None):
    from nucleo.flash import tool_executor_widget_calls as calls
    calls._handle_widget_data_tool(
        {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Quinn", "text": TEXT}},
        _apply_widget_data=apply or (lambda *a, **k: pytest.fail("a message never reaches the inline data door")),
        _brief=None, _frontend=SimpleNamespace(payload_ref=lambda *a, **k: ""), _identify=lambda *_a: "",
        _repeat_repair=None, _say=None,
        _tag_emit=tag_emit or (lambda *a, **k: pytest.fail("a message is never swapped for a show")),
        acted={}, brain=None, clarify={}, deduped={"v": False}, emit=lambda *a, **k: None, escalate_req=esc, text=ORDER)


def test_the_a_ver_order_is_handed_to_the_owner_never_swapped_for_a_show():
    from nucleo.flash import show_guard
    assert show_guard.is_pure_show_request(ORDER), "the sentence still reads as a pure show to the guard…"
    esc = {"v": None, "surface": {}}
    _call(esc)
    assert esc["send_owner"] == {"said": ORDER, "hint": {"contact": "Quinn", "text": TEXT, "_act": "send_to"}}, \
        "…and it is the owner's, with the act the model named"
    assert esc["v"] is None and "send" not in esc, "no worker is commissioned for a message"


def test_disarmed_without_the_hand_off_the_show_guard_takes_the_send(monkeypatch):
    """Disarm: with the hand-off gone, the «a ver» sentence is a show again (seen red)."""
    from nucleo.send import turn
    monkeypatch.setattr(turn, "claim", lambda *a, **k: False)
    monkeypatch.setattr("nucleo.request.send_errand.hand_over", lambda *a, **k: None)
    from nucleo.flash import tool_executor_widget_calls as calls
    monkeypatch.setattr(calls, "_leaving_is_a_task", lambda *a, **k: False)
    shown, esc = [], {"v": None, "surface": {}}
    _call(esc, tag_emit=lambda verb, extra: shown.append((verb, extra.get("id"))), apply=lambda *a, **k: None)
    assert shown == [("show", "mensajeria")] and "send_owner" not in esc

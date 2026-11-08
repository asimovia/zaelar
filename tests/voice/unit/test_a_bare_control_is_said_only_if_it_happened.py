"""A bare control's words are said only if the control happened (operator, 2026-11-08).

Live, on his engine: «pausa» — the model wrote «Paused.», then called the music card's `pause`; the connector refused it
(the account was playing on another device of the house) and the turn said «Paused. I couldn't get that done: …». The
words were written before the act's result, and a deterministic act's result is the only thing that may say it.

Mechanism: `widgets.effects.is_bare_control` (declared: no payload, starts or stops the card's output) + the turn's Hold
(`nucleo/flash/follow_up_pass`): under a SURE verdict naming a bare control the words wait; at the stream's end they are
said if its op landed, dropped if it was refused (the mouth says the refusal), deferred to the turn's end when no op
ran inside the stream (the play tool's lane runs after it, and its own line wins). Nothing reads words.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import follow_up_pass as fup
from widgets import effects


@pytest.mark.parametrize("action,bare", [("pause", True), ("resume", True), ("next", True), ("previous", True),
                                         ("play", False), ("set_volume", False)])
def test_a_bare_control_is_read_from_the_manifest(action, bare):
    assert effects.is_bare_control("musica", action) is bare


def _hold(monkeypatch, target=("musica", "pause")):
    monkeypatch.setattr(fup, "_sure_target", lambda brief: target)
    sent: list = []
    h = fup.Hold({"event": None}, sent.append)
    monkeypatch.setattr("nucleo.request.stop_row.in_play", lambda brief: False)
    monkeypatch.setattr("nucleo.flash.unclear_turn.verdict", lambda brief: "")
    monkeypatch.setattr(fup, "_ready", lambda brief: True)
    monkeypatch.setattr("nucleo.turn.route_by_verdict.decided", lambda *a, **k: False)
    monkeypatch.setattr("nucleo.turn.route_by_verdict.sure_escalate", lambda brief: False)
    return h, sent


def _release(h, result, ran=True):
    async def go():
        tasks = []
        if ran:
            t = asyncio.ensure_future(asyncio.sleep(0, result=result))
            await t
            tasks = [("musica", t)]
        await h.release([{"name": "widget_data", "args": {"widget_id": "musica", "action": "pause"}}],
                        [("musica", "pause")] if ran else [], lambda *a, **k: None, tasks)
    asyncio.run(go())


def test_a_refused_pause_leaves_the_refusal_alone(monkeypatch):
    h, sent = _hold(monkeypatch)
    h.say("Paused.")
    assert sent == [], "the words wait for the control"
    _release(h, {"ok": False, "reason": "elsewhere", "message": "«Camaretas» is using Spotify."})
    assert sent == [], sent


def test_a_pause_that_happened_says_the_words(monkeypatch):
    h, sent = _hold(monkeypatch)
    h.say("Paused.")
    _release(h, {"ok": True, "message": "Paused."})
    assert sent == ["Paused."]


def test_a_control_run_after_the_stream_defers_its_words(monkeypatch):
    """The play tool's lane runs the control after the stream: the words wait for the turn's end, and are said only
    if nothing else was (`flush`) — a refusal line said by the lane wins."""
    h, sent = _hold(monkeypatch)
    h.say("Paused.")
    _release(h, None, ran=False)
    assert sent == [] and h.deferred == "Paused."
    assert fup.flush(h, ["«Camaretas» is using Spotify."], lambda *a, **k: None) == ""
    assert sent == []


def test_an_unheld_verdict_streams_as_before(monkeypatch):
    h, sent = _hold(monkeypatch, target=("musica", "play"))
    h.say("Putting it on.")
    assert sent == ["Putting it on."]

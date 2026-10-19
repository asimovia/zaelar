"""The show is not the act — on the text channel too (demo pass 145, INIT, 2026-10-19).

«Save Quinn and Rowan in my contacts…», a list step and so the TEXT channel, came back as a show of the contacts card
and «I've opened it, though there's nothing in it yet». The voice channel repairs that turn (`after_show`); this one
never asked. The same decision now runs on both, and its call joins the turn's tool calls.
"""
import asyncio
import inspect

from nucleo.flash import card_commission as cc

SHOW = [{"action": "show", "extra": {"id": "contactos"}}]


def _run(monkeypatch, tool_calls, tags=SHOW):
    seen = []

    async def after_show(acted, *, apply_widget_data, **k):
        seen.append(acted["widget_id"])
        apply_widget_data(acted["widget_id"], "add_contact", {"name": "Rowan", "email": "rowan@example.com"})
        return True
    monkeypatch.setattr(cc, "after_show", after_show)
    out = asyncio.run(cc.probe_after_show(tool_calls, tags, "I've opened it, though there's nothing in it yet.",
                                          brief=None, operator_text="Save Rowan in my contacts", spec=None))
    return out, seen


def test_a_card_shown_for_an_order_gets_its_call(monkeypatch):
    calls = []
    out, seen = _run(monkeypatch, calls)
    assert out and seen == ["contactos"]
    assert calls == [{"name": "widget_data", "args": {"widget_id": "contactos", "action": "add_contact",
                                                      "payload": {"name": "Rowan", "email": "rowan@example.com"}}}]


def test_a_card_that_already_got_its_call_or_an_escalation_is_left_alone(monkeypatch):
    for calls in ([{"name": "widget_data", "args": {"widget_id": "contactos", "action": "add_contact"}}],
                  [{"name": "escalate_to_slowbrain", "args": {"request": "x"}}]):
        assert _run(monkeypatch, list(calls)) == (False, [])


def test_the_probe_runs_it():
    from nucleo.flash import probe
    assert "probe_after_show(" in inspect.getsource(probe)

"""The host offers the model its four stops and carries out the one it chose (node 13.121, V2-941, plan v3.2 §3 —
commit 2, the host).

  · the model is offered `stop_voice`, `stop_media`, `stop_run`, `stop_all` beside reply and no_reply, each with no
    parameters and a description of what it stops (declared data); a call to one arrives as an order;
  · the host's hands (`HostStops`): voice, run, all close the attention window; media and all stop what is playing,
    through each card's declared suspension; all cancels his errands in course at the screen's own door — nothing else
    is touched by a narrower stop;
  · the language pack carries the minimal `stopped` line (es «Parado.», en «Stopped.»);
  · the body's conversation is built with these hands, and nothing on the manager's path reads a stop in his words
    any more (the readers are gone).

Disarms seen red: the stops not offered; the window not closed; what plays not stopped; his errands not cancelled; a
narrower stop cancelling errands; the hands not wired.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.conversation_host import stops


def test_the_model_is_offered_the_four_stops_and_a_call_is_an_order():
    from conversation.ports import Command
    from nucleo.conversation_host import model
    offered = {t["function"]["name"]: t["function"] for t in model.tools_for([])}
    for name in ("stop_voice", "stop_media", "stop_run", "stop_all"):
        assert offered[name]["parameters"] == {"type": "object", "properties": {}}
        assert "first order" in offered[name]["description"]

    class Client:
        async def stream(self, messages, *, on_tool_call, metrics, **kw):
            on_tool_call("stop_media", {})
            on_tool_call("reply", {"text": "w9"})
            if False:
                yield ""

    async def run():
        m = model.FastModel(client=Client(), spec=SimpleNamespace(model="m"))
        from conversation.ports import PromptParts
        return [e async for e in m.stream(PromptParts("", "", (), "", (), "voice"), [], run_id="r1", model_id="m")]
    got = asyncio.run(run())
    assert [e.name for e in got if isinstance(e, Command)] == ["stop_media", "reply"]


@pytest.fixture
def hands(monkeypatch):
    from nucleo import dispatch
    from voice import attention
    seen = {"window": 0, "media": 0, "errands": []}
    monkeypatch.setattr(attention, "close_window", lambda src="": seen.__setitem__("window", seen["window"] + 1))
    monkeypatch.setattr(dispatch, "_LOOP", None)
    monkeypatch.setattr(stops, "_media", lambda: seen.__setitem__("media", seen["media"] + 1))
    from nucleo.circuit import ledger
    from nucleo.dispatch import control
    ts = SimpleNamespace(LIVE_STATES=("running",),
                         tasks_where=lambda **kw: [{"id": "t1"}, {"id": "t2"}])
    monkeypatch.setattr(ledger, "store", lambda: ts)
    monkeypatch.setattr(control, "cancel_row", lambda uid, outcome="": seen["errands"].append((uid, outcome)) or "cancelled")
    return seen


@pytest.mark.parametrize("scope, window, media, errands", [
    ("voice", 1, 0, []), ("media", 0, 1, []), ("run", 1, 0, []),
    ("all", 1, 1, [("t1", stops.CANCELLED_BY), ("t2", stops.CANCELLED_BY)])])
def test_each_scope_stops_what_it_names_and_nothing_else(hands, scope, window, media, errands):
    stops.HostStops().stop(scope, "holder")
    assert (hands["window"], hands["media"], hands["errands"]) == (window, media, errands)


def test_what_plays_stops_through_each_cards_declared_suspension(monkeypatch):
    from widgets import producers
    got = []

    async def suspend_all(*, reason="", channel=None, keep=""):
        got.append(reason)
        return ["musica"]
    monkeypatch.setattr(producers, "suspend_all", suspend_all)
    stops._media()
    assert got == [stops.CANCELLED_BY]


def test_the_pack_carries_the_minimal_stopped_line():
    from i18n import langs
    assert (langs.spec("es").stopped, langs.spec("en").stopped) == ("Parado.", "Stopped.")


def test_the_conversation_is_built_with_these_hands_and_no_stop_word_is_read():
    import inspect

    from nucleo.conversation_host import boot, controls, ear_in, guards
    assert "stops=HostStops()" in inspect.getsource(boot.make)
    for gone in ((guards, "split_stop"), (guards, "orders_stop"), (ear_in, "_stopped"), (controls, "typed_line")):
        assert not hasattr(*gone), f"{gone[0].__name__}.{gone[1]} reads his words for a stop"

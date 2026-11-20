"""A routed event enters the conversation manager and its route is obeyed by the host's door (node 13.138, E7d-2, R-2).

The pump routes every event by the one router as before; with the manager on for the account the event is handed to
the conversation as an EVENT envelope — its topic, source, text and declared fields, and the route's verdict, never
his authority — and the host's `Events` door obeys the route by the pump's one body, saying what it did (`resumed`,
`streamed`, `nothing`). With the manager off, the pump obeys it itself; a conversation that cannot open obeys it the
old way. The route's full record stays with the host, by the event's id: a door with no record (a restart) does nothing.
"""
from __future__ import annotations

import asyncio

from conversation.types import Authority, EnvelopeKind
from nucleo.conversation_host import entry, events_in


def _ev():
    from nucleo import events
    return events.event("connector.msg", key="w_chat", text="w_hello", platform="w_chat_app", chat="c1", message="m1")


def test_with_the_manager_on_the_event_enters_as_an_event_and_its_door_obeys_the_route(monkeypatch):
    from nucleo.events import pump
    handed, obeyed = [], []
    monkeypatch.setattr(events_in, "_on", lambda: True)
    monkeypatch.setattr(entry, "_hand", lambda fn: handed.append(fn))
    monkeypatch.setattr(pump, "obey", lambda ev, r, now: obeyed.append((ev["text"], r["as"])))
    monkeypatch.setattr("nucleo.conversation_host.boot.account", lambda: "acct-w")
    route = {"as": "stream", "rules": [{"id": "w_rule"}]}
    assert events_in.give(_ev(), route, 100.0) and not obeyed      # nothing obeyed before the conversation runs it
    got = []

    class _Conv:
        def give(self, env):
            got.append(env)
    handed[0](_Conv())
    env = got[0]
    assert env.kind is EnvelopeKind.EVENT and env.authority is Authority.SOURCE and env.producer.startswith("event:")
    assert env.body.origin == "connector.msg" and env.body.route == {"as": "stream"} and env.body.fields["chat"] == "c1"
    assert asyncio.run(events_in.HostEvents().run("acct-w", env)) == "streamed"
    assert obeyed == [("w_hello", "stream")]
    assert asyncio.run(events_in.HostEvents().run("acct-w", env)) == "nothing" and len(obeyed) == 1   # once


def test_with_the_manager_off_the_pump_obeys_and_a_conversation_that_cannot_open_obeys_the_old_way(monkeypatch):
    from nucleo.events import once, pump, route as flow
    obeyed, handed = [], []
    monkeypatch.setattr(once, "first", lambda ev: True)
    monkeypatch.setattr(flow, "route", lambda ev: {"as": "nothing"})
    monkeypatch.setattr(pump, "obey", lambda ev, r, now: obeyed.append(r["as"]))
    monkeypatch.setattr(events_in, "_on", lambda: False)
    asyncio.run(pump.publish(_ev(), now=1.0))
    assert obeyed == ["nothing"]
    monkeypatch.setattr(events_in, "_on", lambda: True)
    monkeypatch.setattr(entry, "_hand", lambda fn: handed.append(fn))
    monkeypatch.setattr("nucleo.conversation_host.boot.account", lambda: "acct-w")
    asyncio.run(pump.publish(_ev(), now=2.0))
    assert obeyed == ["nothing"] and len(handed) == 1
    handed[0].fallback()
    assert obeyed == ["nothing", "nothing"]

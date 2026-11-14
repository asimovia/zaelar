"""T575 · the two-plató run: two engines in one process over the fake network.

discover → proposal → yes → request → card → accept → message → query denied → grant → reply → live share
samples → revoke → denied. Zero model calls; the observed multiset of ops is the declared expectation (T590 a),
and silencing one handler's row turns it red (T590 c)."""
from __future__ import annotations

import sys
from collections import Counter

import pytest

from a2a import events
from a2a.relationships import IllegalTransition

LLM_MODULES = ("anthropic", "openai", "nucleo.flash", "nucleo.llm", "litellm", "google.generativeai")

EXPECTED_A = Counter({
    "publish": 1, "discover": 1, "propose": 1, "propose_answer": 1, "request": 1, "accept": 1, "pull": 5,
    "msg": 2, "query": 3, "denied": 2, "reply": 1, "live_open": 1, "live_sample": 3, "grant_notice": 1,
    "revoke": 2, "live_close": 1,
})
EXPECTED_B = Counter({
    "publish": 1, "discover": 1, "request": 1, "request_card": 1, "accept": 1, "pull": 7, "msg": 2,
    "query": 3, "denied": 2, "grant": 1, "reply": 1, "revoke": 2, "live_open": 1, "live_read": 2,
    "live_close": 1,
})


def run_scenario(pair, net, clock):
    a, b = pair(a_answers={"propose": "ask"}, b_answers={"request": "accept"},
                busy=lambda f, t: [{"start": "2026-11-15T18:00", "end": "2026-11-15T19:00", "title": "Gym"}])
    # discovery: both publish, B looks first (records interest), A finds the mutual match and says yes
    a.publish_hashes(emails=["ana@example.com"])
    b.publish_hashes(phones=["+34600112233"])
    b.discover([{"cid": "ana", "name": "Ana", "emails": ["ana@example.com"]}])
    a.discover([{"cid": "marta", "name": "Marta", "phones": ["+34 600 11 22 33"]}], trigger="contact")
    assert a.rels.by_contact("marta").status == "outgoing"
    b.pull()                                            # request → card → accept
    assert [c["type"] for c in b.cards] == ["request"] and b.rels.get(a.me.did).status == "accepted"
    a.pull()                                            # accept in
    assert a.rels.by_contact("marta").status == "accepted"
    assert a.rels.by_contact("marta").rel == b.rels.get(a.me.did).rel        # one rel id on both machines
    # messages both ways (D7: messages is the default on accept)
    assert a.send("marta", "¿Cenamos el viernes?")
    b.pull()
    assert b.inbox()[0]["text"] == "¿Cenamos el viernes?" and b.inbox()[0]["trust"] == "contact"
    b.send(a.me.did, "Sí, a las 21")
    a.pull()
    # calendar: denied, then granted, then intervals only
    q1 = a.ask("marta", "calendar", "freebusy", {"from": "2026-11-15", "to": "2026-11-16"})
    b.pull(); a.pull()
    assert a.answer(q1)["status"] == "denied"
    b.grant(a.me.did, "calendar", ["see"], how="voice")
    q2 = a.ask("marta", "calendar", "freebusy", {"from": "2026-11-15", "to": "2026-11-16"})
    b.pull(); a.pull()
    assert a.answer(q2)["data"] == [{"start": "2026-11-15T18:00", "end": "2026-11-15T19:00"}]
    assert a.status()["shared_with_me"]["marta"]["calendar"]["verbs"] == ["see"]
    # live share: A shares the ride with Marta, three samples, Marta reads them
    sid = a.live_open("marta", "activity.live", ttl_s=3600)
    for i in range(3):
        clock.advance(10)
        assert a.live_push(sid, {"lat": 43.26 + i / 1000, "lon": -2.93, "km": i * 0.5})
    b.pull()
    got = b.live_read(sid)
    assert [s["body"]["km"] for s in got["samples"]] == [0.0, 0.5, 1.0]
    assert "43.26" not in str(net.shares)              # samples are E2E sealed
    # revoke: the share closes, Marta's next read says closed, the calendar is denied again
    b.revoke(a.me.did, "calendar")
    a.revoke("marta", "activity.live")
    assert a.live_push(sid, {"km": 9}) is None
    b.pull()
    assert b.live_read(sid)["closed"] is True
    q3 = a.ask("marta", "calendar", "freebusy", {"from": "2026-11-15", "to": "2026-11-16"})
    b.pull(); a.pull()
    assert a.answer(q3)["status"] == "denied"
    return a, b


def test_the_two_plato_run(pair, net, clock, rows):
    before = {m for m in sys.modules if m.startswith(LLM_MODULES)}
    a, b = run_scenario(pair, net, clock)
    assert {m for m in sys.modules if m.startswith(LLM_MODULES)} == before, "I3: the protocol costs no model call"
    assert Counter(rows.ops(a)) == EXPECTED_A
    assert Counter(rows.ops(b)) == EXPECTED_B
    for r in rows:                                       # T590 d
        assert a.me.did not in str(r) and b.me.did not in str(r)
        assert "sig" not in r and "sealed" not in str(r)


def test_silencing_one_handler_row_turns_the_run_red(pair, net, clock, rows, monkeypatch):
    from a2a.handlers import messages
    real = messages.on_text

    def mute(agent, env):
        monkeypatch.setattr(agent, "emit", lambda *a, **k: None)
        try:
            real(agent, env)
        finally:
            monkeypatch.undo()
    monkeypatch.setitem(__import__("a2a.handlers", fromlist=["HANDLERS"]).HANDLERS, "msg.text", mute)
    a, b = run_scenario(pair, net, clock)
    assert Counter(rows.ops(b)) != EXPECTED_B


def test_after_disconnect_nothing_passes(pair, net, clock):
    a, b = run_scenario(pair, net, clock)
    a.disconnect("marta")
    b.pull()
    assert b.rels.get(a.me.did).status == "revoked"
    with pytest.raises(IllegalTransition):
        b.send(a.me.did, "¿sigues ahí?")

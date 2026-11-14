"""T578/T579 · cadence, the ⏻, and the wake gate (only the network key wakes)."""
from __future__ import annotations

import json

from a2a.identity import Identity
from a2a.jobs import Jobs
from a2a.server_api import WakeGate
from tests.a2a.conftest import connected


def test_idle_throttle_active_window_and_stopped(pair, net, clock):
    a, b = connected(*pair())
    j = Jobs(b, clock=clock)
    assert "pull" in j.tick()
    clock.advance(60)
    assert "pull" not in j.tick()                    # idle: no second pull inside 15 min
    a.send("marta", "hola")
    clock.advance(900)
    j.tick()                                          # brings the message → active
    clock.advance(31)
    assert "pull" in j.tick()
    j.stopped = True
    clock.advance(10_000)
    assert j.tick() == [] and j.wake() == 0


def test_a_restart_fires_an_overdue_job_once(pair, clock):
    a, b = pair()
    j = Jobs(b, clock=clock)
    j.tick()
    clock.advance(5 * 86400)
    ran = j.tick()
    assert ran.count("discover") == 1 and ran.count("pull") == 1


def test_contact_event_is_debounced_and_shares_the_discovery_path(pair, clock, rows):
    a, b = pair()
    j = Jobs(b, contacts=lambda: [{"cid": "ana", "emails": ["ana@example.com"]}], clock=clock)
    j.tick()
    j.contact_event("ana"); j.contact_event("ana")
    assert "discover:contact" not in j.tick()
    clock.advance(61)
    assert "discover:contact" in j.tick()
    assert [r["trigger"] for r in rows if r["op"] == "discover"] == ["daily", "contact"]


def test_unsigned_or_foreign_wake_is_401_and_does_not_pull(pair, clock, rows):
    a, b = pair()
    j = Jobs(b, clock=clock)
    net_key = Identity.generate()
    gate = WakeGate(net_key.pub_b64, clock=clock)
    body = json.dumps({"kind": "mail"})
    pulls = len([r for r in net_calls(b)])
    assert gate.handle(j, {}, body)[0] == 401
    forged = Identity.generate().mk_sig("POST", "/api/a2a/wake", body, ts=int(clock()))
    assert gate.handle(j, {"MeshKore-Sig": forged}, body)[0] == 401
    assert len(net_calls(b)) == pulls
    good = net_key.mk_sig("POST", "/api/a2a/wake", body, ts=int(clock()))
    assert gate.handle(j, {"MeshKore-Sig": good}, body)[0] == 202
    assert len(net_calls(b)) == pulls + 1
    assert gate.handle(j, {"MeshKore-Sig": good}, body)[0] == 401          # nonce replay
    assert [r["sig_ok"] for r in rows if r["op"] == "wake"] == [False, False, True, False]


def net_calls(agent):
    return [c for c in agent.mailbox.net.calls if c == (agent.me.did, "mail.pull")]


def test_a_dead_network_is_one_event_and_the_cadence_goes_on(pair, net, clock, rows):
    a, b = pair()
    j = Jobs(b, clock=clock)
    net.down = True
    j.tick()
    assert [r["ok"] for r in rows if r["op"] == "pull"] == [False]
    clock.advance(901)
    net.down = False
    assert "pull" in j.tick()

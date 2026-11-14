"""T570 · the relationship store and its state machine."""
from __future__ import annotations

import pytest

from a2a.relationships import IllegalTransition, Relationships

D1, D2 = "did:key:" + "A" * 43 + "=", "did:key:" + "B" * 43 + "="


def test_the_state_survives_a_restart(tmp_path, clock):
    s = Relationships(tmp_path, clock=clock)
    s.outgoing(D1, contact_id="marta", name="Marta")
    s.set_cursor(7)
    s.mark_seen("e1")
    s2 = Relationships(tmp_path, clock=clock)
    r = s2.get(D1)
    assert (r.status, r.contact_id, s2.cursor, "e1" in s2.seen()) == ("outgoing", "marta", 7, True)


def test_request_card_then_accept(tmp_path, clock):
    s = Relationships(tmp_path, clock=clock)
    r, outcome = s.incoming(D1, rel="r1", name="Ana")
    assert (outcome, r.status, r.rel) == ("card", "incoming", "r1")
    assert s.accept(D1).status == "accepted"
    with pytest.raises(IllegalTransition):
        s.accept(D1)


def test_crossing_requests_resolve_to_accepted(tmp_path, clock):
    s = Relationships(tmp_path, clock=clock)
    s.outgoing(D1)
    r, outcome = s.incoming(D1)
    assert (outcome, r.status) == ("crossing", "accepted")
    s.incoming(D2)
    r, crossing = s.outgoing(D2)
    assert crossing and r.status == "accepted"


def test_a_request_is_honoured_once_a_day_and_a_decline_holds_30_days(tmp_path, clock):
    s = Relationships(tmp_path, clock=clock)
    s.incoming(D1)
    assert s.incoming(D1)[1] == "rate_limited"
    s.decline(D1)
    clock.advance(2 * 86400)
    assert s.incoming(D1)[1] == "held"
    clock.advance(29 * 86400)
    assert s.incoming(D1)[1] == "card"


def test_revoke_then_reconnect(tmp_path, clock):
    s = Relationships(tmp_path, clock=clock)
    s.incoming(D1)
    s.accept(D1)
    assert s.revoke(D1).status == "revoked"
    assert s.outgoing(D1)[0].status == "outgoing"

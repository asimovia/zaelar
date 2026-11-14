"""T572/T574 · inbound gate and handlers: strangers dropped unread, unknown kinds dropped, queries by grant."""
from __future__ import annotations

from a2a.envelope import Envelope
from a2a.handlers import dispatch
from a2a.identity import Identity
from a2a.transport.base import Mail
from tests.a2a.conftest import connected


def test_a_stranger_produces_no_card_and_is_not_decrypted(pair, rows):
    a, b = pair()
    stranger = Identity.generate()
    wire = Envelope("msg.text", stranger.did, b.me.did, {"text": "buy now"}).seal(stranger)
    assert dispatch(b, Mail(1, stranger.did, 0, wire)) == "dropped:stranger"
    assert b.cards == [] and b.inbox() == []
    drop = [r for r in rows if r["op"] == "dropped"][-1]
    assert drop["reason"] == "stranger" and "buy" not in str(drop)


def test_unknown_kind_and_forged_sender_are_dropped(pair, rows):
    a, b = connected(*pair())
    w = Envelope("msg.text", a.me.did, b.me.did, {"text": "hi"}, ts=int(a.clock())).seal(a.me)
    assert dispatch(b, Mail(9, a.me.did, 0, dict(w, kind="evil.kind"))) == "dropped:unknown_kind"
    other = Identity.generate()
    b.rels.ensure(other.did, status="accepted")
    assert dispatch(b, Mail(10, other.did, 0, w)) == "dropped:bad_sig"
    assert dispatch(b, Mail(11, a.me.did, 0, w)) == "msg.text"
    assert dispatch(b, Mail(12, a.me.did, 0, w)) == "dropped:replay"


def test_a_query_without_grant_is_denied_and_with_grant_carries_no_titles(pair, clock):
    busy = lambda f, t: [{"start": "2026-11-15T10:00", "end": "2026-11-15T11:00", "title": "Dentist Dr. X"}]
    a, b = connected(*pair(busy=busy))
    q = a.ask("marta", "calendar", "freebusy", {"from": "2026-11-15", "to": "2026-11-16"})
    b.pull(); a.pull()
    assert a.answer(q)["status"] == "denied" and a.answer(q)["reason"] == "no_row"
    b.grant("ana", "calendar", ["see"])
    q = a.ask("marta", "calendar", "freebusy", {"from": "2026-11-15", "to": "2026-11-16"})
    b.pull(); a.pull()
    ans = a.answer(q)
    assert ans["status"] == "answered" and ans["data"] == [{"start": "2026-11-15T10:00", "end": "2026-11-15T11:00"}]
    assert "Dentist" not in str(a.state)


def test_profile_reply_carries_only_the_public_set(pair):
    a, b = connected(*pair(profile=lambda: {"name": "Marta", "city": "Bilbao"}))
    b.grant("ana", "profile", ["see"])
    q = a.ask("marta", "profile")
    b.pull(); a.pull()
    assert a.answer(q)["data"] == {"name": "Marta", "city": "Bilbao"}


def test_messages_need_the_relationship_on_the_network_too(pair):
    a, b = pair()
    import pytest
    from a2a.relationships import IllegalTransition
    a.connect(b.me.did, contact_id="marta")
    with pytest.raises(IllegalTransition):
        a.send("marta", "hola")


def test_an_outbound_text_the_scanner_blocks_never_leaves(pair, net, rows):
    a, b = connected(*pair())
    a.scan_outbound = lambda text: "secret" if "sk-" in text else None
    before = len(net.boxes[b.me.did])
    assert a.send("marta", "my key is sk-123") is False
    assert len(net.boxes[b.me.did]) == before
    assert rows[-1]["op"] == "msg_blocked" and "sk-" not in str(rows[-1])

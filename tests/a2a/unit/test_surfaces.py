"""V2-866 F3 · the owner's surfaces: widget-declared items, durable consent cards, the turn's A2A tools (offered by
state, read out by code), the contact's `a2a` block and the `contact.saved` hook."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import a2a
from a2a.items import ItemRegistry, declare_manifest
from tests.a2a.conftest import connected

ROOT = Path(__file__).resolve().parents[3]


def test_manifests_declare_shareable_items_and_never_the_forbidden_roots():
    from server import a2a_wiring as w
    reg = ItemRegistry()
    ids = w.declare_widget_items(reg)
    assert {"calendar", "agenda.list", "activity.history", "activity.live"} <= set(ids)
    assert reg.get("calendar").owner_widget == "agenda" and "freebusy" in reg.get("calendar").projections
    for man in ROOT.glob("widgets/*/manifest.json"):
        for e in json.loads(man.read_text()).get("shareable") or []:
            assert e["id"].split(".")[0] not in a2a.items.NEVER_SHAREABLE
    assert declare_manifest(ItemRegistry(), "x", [{"id": "memory.all", "kind": "collection", "verbs": ["see"]},
                                                   {"id": "y", "kind": "bogus"}], {}) == []


class _Say:
    def __getattr__(self, k):
        return {"a2a_sent": "sent {name}", "a2a_sharing_line": "with {name}: {items}",
                "a2a_sharing_none": "nothing", "a2a_not_connected": "no {name}"}.get(k, k)


@pytest.fixture
def live(pair):
    a, b = connected(*pair())
    a2a.set_runtime(a, None)
    yield a, b
    a2a.set_runtime(None, None)


def test_turn_tools_reach_the_agent_and_are_read_out_by_code(live):
    from nucleo.flash import tools_a2a as t
    a, b = live
    assert t.live()
    out = t.run("a2a_send", {"to": "marta", "text": "hola"}, lambda *a, **k: None)
    assert out["ok"] and t.line("a2a_send", out, {"to": "Marta"}, _Say()) == "sent Marta"
    b.pull()
    assert b.inbox()[0]["text"] == "hola"
    t.run("a2a_grant", {"to": "Marta", "item": "calendar"}, lambda *a, **k: None)
    out = t.run("a2a_read", {"what": "sharing"}, lambda *a, **k: None)
    assert "calendar" in t.line("a2a_read", out, {}, _Say())
    out = t.run("a2a_send", {"to": "Pepe", "text": "x"}, lambda *a, **k: None)
    assert t.line("a2a_send", out, {"to": "Pepe"}, _Say()) == "no Pepe"


def test_tools_are_absent_while_off():
    from nucleo.flash import tools_a2a as t
    a2a.set_runtime(None, None)
    assert not t.live()
    assert t.run("a2a_read", {"what": "status"}, lambda *a, **k: None)["error"] == "a2a_off"


def test_a_request_becomes_a_durable_card_answered_by_its_button(pair, tmp_path):
    from server.a2a_cards import Cards
    a, b = pair()
    cards = Cards(tmp_path / "cards")
    b.asker, cards.agent = cards.asker, b
    a.connect(b.me.did, contact_id="marta", name="Marta")
    b.pull()
    pending = Cards(tmp_path / "cards").pending()           # survives a restart
    assert len(pending) == 1 and pending[0]["type"] == "request"
    assert cards.answer(pending[0]["id"], True)["ok"]
    assert b.rels.get(a.me.did).status == "accepted"
    assert not cards.answer(pending[0]["id"], True)["ok"]   # answered once


def test_the_contact_block_and_the_saved_hook(live, monkeypatch):
    a, _b = live
    blk = a2a.contact_block("marta")
    assert blk["status"] == "accepted" and any(g["item"] == "messages" for g in blk["grants"])
    from widgets.contactos import a2a_actions
    seen = []
    import bus
    monkeypatch.setattr(bus, "emit_sync", lambda topic, payload=None: seen.append((topic, payload)))
    out = a2a_actions.after("update_contact", {}, {"ok": True, "result": {"contact": {"id": "marta"}}})
    assert seen == [("contact.saved", {"cid": "marta"})]
    assert out["result"]["contact"]["a2a"]["status"] == "accepted"


def test_the_bus_topic_debounces_one_lookup():
    from server import a2a_api

    class J:
        got = []

        def contact_event(self, cid):
            self.got.append(cid)
    a2a_api._state["jobs"] = J()
    try:
        a2a_api._on_bus({"topic": "contact.saved", "payload": {"cid": "7"}})
        a2a_api._on_bus({"topic": "other", "payload": {"cid": "8"}})
        assert J.got == ["7"]
    finally:
        a2a_api._state["jobs"] = None


def test_the_consent_classes_are_declared():
    from nucleo.events import vocabulary as v
    for verb in a2a.items.VERBS:
        assert v.declared(f"a2a.{verb}")


def test_a2a_send_crosses_the_one_consent_door_with_the_contact_as_subject(live, monkeypatch):
    """T583 · `a2a_send` asks `consent.decide_act("messaging.send_new@a2a", subject=cid)`: «never» refuses, «ask»
    holds it unsent, a clear verdict sends. Disarm: skip the door → the refused message reaches Marta."""
    from nucleo import consent
    from nucleo.flash import tools_a2a as t
    a, b = live
    seen = []

    def door(cls, **k):
        seen.append((cls, k.get("channel"), k.get("subject")))
        return {"verdict": verdict[0]}
    monkeypatch.setattr(consent, "decide_act", door)
    verdict = [consent.REFUSE]
    out = t.run("a2a_send", {"to": "Marta", "text": "no"}, lambda *a, **k: None)
    assert out == {"ok": False, "error": "refused"} and seen[-1] == ("messaging.send_new", "a2a", "marta")
    assert t.line("a2a_send", out, {"to": "Marta"}, _Say()) == "a2a_send_refused"
    verdict = [consent.ASK_CONSENT]
    assert t.run("a2a_send", {"to": "Marta", "text": "wait"}, lambda *a, **k: None)["error"] == "held"
    b.pull()
    assert b.inbox() == []
    verdict = [consent.RUN]
    assert t.run("a2a_send", {"to": "Marta", "text": "ok"}, lambda *a, **k: None)["ok"]
    b.pull()
    assert [m["text"] for m in b.inbox()] == ["ok"]

"""Contacts: a source is a preference, never a gate, and each act declares its real end state (operator, 2026-11-08).

  · «sync my contacts» with Google not reachable answered a bare error: now the card still answers with what it holds
    and the reply OFFERS the sources that are connected — importing from one of them is his choice;
  · `sync_source` naming a source that is not linked offers the linked ones, and imports nothing on his behalf;
  · add / remove / set_channel / update / create_group declare their `done_when`, and each reads the real outcome.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def cd(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data, gcontacts, sources
    monkeypatch.setattr(gcontacts, "svc", lambda: None)               # Google is not reachable
    monkeypatch.setattr(sources, "connected", lambda s: s == "telegram")
    return data


# ── a source that is down is an offer ───────────────────────────────────────────────────────────────────────────

def test_a_sync_without_google_keeps_the_card_and_offers_the_connected_sources(cd):
    cd.apply_action("add_contact", {"name": "Rowan Example"})
    r = cd.apply_action("sync_contacts", {})
    assert r["ok"] is False and r["offer"] == ["telegram"]
    assert "Telegram" in r["message"], "the offer names the connected source"
    assert r["count"] == 1 and "sync" in r, "the card's view travels with the refusal"
    assert [c["name"] for c in cd.load_db()["contacts"]] == ["Rowan Example"], "nothing imported on his behalf"


def test_a_named_source_that_is_not_linked_offers_the_linked_ones(cd, monkeypatch):
    from widgets.contactos import sources
    asked = []
    monkeypatch.setattr(sources, "_payload", lambda s: asked.append(s) or {"ok": True, "contacts": []})
    r = cd.apply_action("sync_source", {"source": "whatsapp"})
    assert r["ok"] is False and r["error"] == "source_not_connected" and r["offer"] == ["telegram"]
    assert "WhatsApp" in r["message"] and "Telegram" in r["message"]
    assert asked == [], "no other source is asked on his behalf"


def test_with_nothing_linked_there_is_no_offer(cd, monkeypatch):
    from widgets.contactos import sources
    monkeypatch.setattr(sources, "connected", lambda s: False)
    r = cd.apply_action("sync_contacts", {})
    assert r["ok"] is False and r["offer"] == []


# ── each act declares its real end state ────────────────────────────────────────────────────────────────────────

def _check(action, payload):
    from nucleo.circuit import spec, verify
    dw = spec.render("contactos", action, payload)
    assert dw, f"{action} declares an end state"
    return dw, verify.check


@pytest.mark.parametrize("name", ["Iván Petrenko", "Quinn Example"])
def test_add_contact_is_done_when_the_person_is_in_the_directory(cd, name):
    dw, check = _check("add_contact", {"name": name})
    assert check(dw) is False
    cd.apply_action("add_contact", {"name": name})
    assert check(dw) is True


def test_remove_contact_is_done_when_the_row_is_gone(cd):
    cd.apply_action("add_contact", {"name": "Rowan Example"})
    cid = cd.load_db()["contacts"][0]["id"]
    dw, check = _check("remove_contact", {"contactId": cid})
    assert check(dw) is False
    cd.apply_action("remove_contact", {"contactId": cid})
    assert check(dw) is True


def test_set_channel_is_done_when_the_contact_has_that_channel(cd):
    cd.apply_action("add_contact", {"name": "Rowan Example"})
    cid = cd.load_db()["contacts"][0]["id"]
    dw, check = _check("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@rowan"})
    assert check(dw) is False
    cd.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@rowan"})
    assert check(dw) is True


def test_update_contact_is_done_when_the_row_carries_the_new_value(cd):
    cd.apply_action("add_contact", {"name": "Rowan Example", "city": "Soria"})
    cid = cd.load_db()["contacts"][0]["id"]
    dw, check = _check("update_contact", {"contactId": cid, "city": "Los Angeles"})
    assert check(dw) is False
    cd.apply_action("update_contact", {"contactId": cid, "city": "Los Angeles"})
    assert check(dw) is True


def test_create_group_is_done_when_the_group_exists(cd):
    dw, check = _check("create_group", {"name": "Padres del colegio"})
    assert check(dw) is False
    cd.apply_action("create_group", {"name": "Padres del colegio"})
    assert check(dw) is True

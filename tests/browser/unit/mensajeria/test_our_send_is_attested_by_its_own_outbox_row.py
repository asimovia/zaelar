"""A send is attested by OUR order's row, and a channel is a preference, never a gate (operator, 2026-11-08).

Measured flaw: `send_to` / `forward` / `send_draft` declared their end state as «a new row in `sent` naming the
contact». A message he types on his own phone to that person, or an autoresponder's, lands in the same thread and
satisfied it — another actor met OUR order's end state. Now every order queued by this card opens a row of the
`outbox` collection (its `ref`, who it was for, the platform, the state the connector's echo or failure settles), and
the end state is a NEW outbox row for that contact in state `sent`.

The four principles, per case below:
  · the end state describes OUR outcome (a phone message is not it; our settled row is);
  · with no channel named, a preferred channel whose link is down is skipped for a connected one the contact has;
  · a channel he NAMED that is down is an OFFER naming the connected alternatives — nothing is queued;
  · a send that failed is an OFFER of the contact's other connected channels — nothing is resent.
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def box(tmp_path, monkeypatch):
    """Isolated stores: the messaging queue and the directory both live under the patched widgets data dir."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    cd.apply_action("add_contact", {"name": "Rowan Example", "email": "rowan@example.com", "phone": "+34600111222"})
    cid = cd.load_db()["contacts"][0]["id"]
    cd.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@rowan_example"})
    cd.apply_action("set_channel", {"contactId": cid, "platform": "whatsapp", "handle": "+34600111222",
                                    "chatId": "34600111222@s.whatsapp.net", "preferred": False})
    return md


def _links(md, **status):
    db = md.load_db()
    for p, st in status.items():
        db.setdefault("platforms", {})[p] = {"status": st, "qr": None}
    md.store.save(md.WIDGET_ID, db)


def _settle(md, ref, ok=True):
    from widgets.mensajeria import sent
    db = md.load_db()
    assert sent.outbox_settle(db, ref, ok, "" if ok else "bridge refused")
    md.store.save(md.WIDGET_ID, db)


def _typed_on_his_phone(md, platform, chat_id, name, body):
    db = md.load_db()
    th = db.setdefault("threads", {}).setdefault(f"{platform}|{chat_id}", {"name": name, "msgs": []})
    th["msgs"].append({"id": f"phone-{len(th['msgs'])}", "dir": "out", "who": "Tú", "body": body, "ts": time.time()})
    md.store.save(md.WIDGET_ID, db)


# ── every order opens its own row ───────────────────────────────────────────────────────────────────────────────

def test_a_send_to_opens_an_outbox_row_naming_who_it_was_for(box):
    from widgets import rows
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "running late"})
    ref = r["result"]["ref"]
    row = next(x for x in box.view_data()["outbox"] if x["ref"] == ref)
    assert row["name"] == "Rowan Example" and row["contactId"] and row["platform"] == "telegram"
    assert row["state"] == "queued"
    assert rows.spec("mensajeria", "outbox").get("id") == "ref", "the collection names its rows by the order's ref"


def test_a_reply_order_also_names_itself(box):
    db = box.load_db()
    box._outbound.enqueue_reply(db, {"platform": "telegram", "chatId": "1000000017", "name": "Rowan"}, "ok")
    ref = db["pending_reply"][-1].get("ref")
    assert ref and any(r["ref"] == ref for r in db["outbox"]), "a reply carries a ref and opens its row"


# ── the end state is OUR outcome ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("contact,text", [("Rowan", "voy de camino"), ("Rowan Example", "on my way")])
def test_a_message_he_types_on_his_phone_does_not_meet_our_send(box, contact, text):
    from nucleo.circuit import spec, verify
    dw = spec.render("mensajeria", "send_to", {"contact": contact, "text": text})
    r = box.apply_action("send_to", {"contact": contact, "text": text})
    assert verify.check(dw) is False, "queued is not sent"
    _typed_on_his_phone(box, "telegram", "1000000017", "Rowan Example", text)
    assert verify.check(dw) is False, "his own message to the same person is another actor's, not our order's"
    _settle(box, r["result"]["ref"])
    assert verify.check(dw) is True, "our order's row, settled sent by the connector's echo"


def test_a_failed_order_never_meets_its_end_state(box):
    from nucleo.circuit import spec, verify
    dw = spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "hola"})
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "hola"})
    _settle(box, r["result"]["ref"], ok=False)
    assert verify.check(dw) is False


def test_a_named_channel_is_part_of_the_end_state(box):
    from nucleo.circuit import spec
    dw = spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "hi", "channel": "whatsapp"})
    assert dw["where"]["platform"] == "whatsapp"
    assert "platform" not in spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "hi"})["where"]


# ── forward goes by the contact's channel, not mail by default ──────────────────────────────────────────────────

def test_forward_with_no_channel_named_uses_the_contacts_preferred_channel(box, monkeypatch):
    monkeypatch.setattr(box._outbound, "attachments_of", lambda db, ref: ["/tmp/invoice.pdf"])
    r = box.apply_action("forward", {"contact": "Rowan", "text": "la factura", "n": 1})
    assert r["ok"] and r["result"]["channel"] == "telegram", "his preferred channel, not email by default"
    r = box.apply_action("forward", {"contact": "Rowan", "text": "the invoice", "n": 1, "channel": "email"})
    assert r["result"]["channel"] == "email", "a channel he names is honoured"


# ── a channel is a preference, never a gate ─────────────────────────────────────────────────────────────────────

def test_a_preferred_channel_that_is_down_is_skipped_for_a_connected_one(box):
    _links(box, telegram="off", whatsapp="connected", email="off")
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "¿cenamos?"})
    assert r["ok"] and r["result"]["channel"] == "whatsapp"


def test_a_named_channel_that_is_down_is_an_offer_and_nothing_is_queued(box):
    _links(box, telegram="off", whatsapp="connected", email="connected")
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "hi", "channel": "telegram"})
    assert r["ok"] is False and r["error"] == "channel_down"
    assert sorted(r["offer"]) == ["email", "whatsapp"]
    assert "Telegram" in r["message"] and "WhatsApp" in r["message"]
    assert not box.load_db().get("pending_send"), "an offer never sends through another channel on his behalf"


def test_with_no_link_reported_the_usual_choice_stands(box):
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "hi", "channel": "email"})
    assert r["ok"] and r["result"]["channel"] == "email", "unknown link state is not «down»"


def test_a_failed_send_offers_the_contacts_other_connected_channels_and_resends_nothing(box, monkeypatch):
    from widgets.mensajeria import owner
    _links(box, telegram="connected", whatsapp="connected", email="off")
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "hola"})
    ref = r["result"]["ref"]
    db = box.load_db()
    order = dict(db["pending_send"][0])
    db["pending_send"] = []
    box.store.save(box.WIDGET_ID, db)
    notes = []
    monkeypatch.setattr(owner, "_note", lambda text: notes.append(text))
    owner._settle(ref, False, "bridge refused")
    alts = owner._offer_after_failure({**order, "reason": "bridge refused"})
    assert alts == ["whatsapp"]
    row = next(x for x in box.load_db()["outbox"] if x["ref"] == ref)
    assert row["state"] == "failed" and row["offer"] == ["whatsapp"]
    assert len(notes) == 1 and "WhatsApp" in notes[0] and "NO lo reenvíes" in notes[0]
    assert not box.load_db().get("pending_send"), "nothing is resent through the other channel"

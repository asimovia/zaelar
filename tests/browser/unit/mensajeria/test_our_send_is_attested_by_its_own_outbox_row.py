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


# ── «nothing is connected» is a fact once every connector reported it ───────────────────────────────────────────

def _reported(md, **status):
    """Every platform's link as its connector reports it (`reported`), the ones not given «off»."""
    from connectors.messaging import store as ms
    db = md.load_db()
    for p in ms.PLATFORMS:
        db.setdefault("platforms", {})[p] = {"status": status.get(p, "off"), "qr": None, "detail": None,
                                             "reported": True}
    md.store.save(md.WIDGET_ID, db)


@pytest.mark.parametrize("payload", [{"contact": "Rowan", "text": "hi", "channel": "telegram"},
                                     {"contact": "Rowan", "text": "hola"}], ids=["named", "not-named"])
def test_with_every_link_reported_and_none_connected_a_send_is_refused_and_nothing_is_queued(box, payload):
    from widgets.mensajeria.outbound import targets
    _reported(box)
    assert targets.connected_platforms() == set(), "every connector reported and none is up: known, not unknown"
    r = box.apply_action("send_to", dict(payload))
    assert r["ok"] is False and r["error"] == "channel_down", r
    assert r.get("message"), "the refusal carries the card's own line"
    assert not box.load_db().get("pending_send"), "an order queued on a link that never drains it"


def test_a_contact_whose_only_channel_is_down_is_refused_while_another_platform_is_up(box):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Sasha Sample"})
    sid = next(c["id"] for c in cd.load_db()["contacts"] if c["name"] == "Sasha Sample")
    cd.apply_action("set_channel", {"contactId": sid, "platform": "telegram", "handle": "@sasha_sample"})
    _links(box, telegram="off", whatsapp="connected", email="off")
    r = box.apply_action("send_to", {"contact": "Sasha Sample", "text": "¿cenamos?"})
    assert r["ok"] is False and r["error"] == "channel_down", r
    assert r["offer"] == [], "she has no other channel to offer"
    assert not box.load_db().get("pending_send"), "queued on a link that is down"


def test_a_resting_store_nobody_reported_keeps_the_usual_choice(box):
    from widgets.mensajeria.outbound import targets
    _links(box, telegram="off", whatsapp="off", email="off")          # the resting value: no `reported`
    assert targets.connected_platforms() is None
    r = box.apply_action("send_to", {"contact": "Rowan", "text": "hi"})
    assert r["ok"] and r["result"]["channel"] == "telegram", r


def test_one_unreported_platform_keeps_the_state_unknown(box):
    from widgets.mensajeria.outbound import targets
    _reported(box)
    db = box.load_db()
    db["platforms"]["email"].pop("reported")
    box.store.save(box.WIDGET_ID, db)
    assert targets.connected_platforms() is None


def test_a_reported_off_is_written_once_and_the_same_report_again_is_no_save(box, monkeypatch):
    from connectors.messaging import store as ms
    assert not (box.load_db().get("platforms", {}).get("whatsapp") or {}).get("reported")
    ms.set_platform_status("whatsapp", "off")
    assert box.load_db()["platforms"]["whatsapp"]["reported"] is True
    saves = []
    monkeypatch.setattr(ms, "save", lambda db: saves.append(db) or db)
    ms.set_platform_status("whatsapp", "off")
    assert saves == [], "the same report re-saved: the change gate floods the stream"


def test_the_owner_reports_every_switched_off_link_and_leaves_a_switched_on_one(box, monkeypatch):
    from config import connectors as switch
    from connectors.messaging import store as ms
    from widgets.mensajeria import owner
    from widgets.mensajeria.outbound import targets
    monkeypatch.setattr(switch, "enabled", lambda p: False)
    owner._Owner()._report_switched_off()
    plats = box.load_db()["platforms"]
    assert all(plats[p].get("reported") and plats[p]["status"] == "off" for p in ms.PLATFORMS), plats
    assert targets.connected_platforms() == set()
    ms.set_platform_status("telegram", "connected")
    monkeypatch.setattr(switch, "enabled", lambda p: p == "telegram")
    owner._Owner()._report_switched_off()
    assert box.load_db()["platforms"]["telegram"]["status"] == "connected", "a switched-on link is its connector's"
    assert targets.connected_platforms() == {"telegram"}


def test_disarmed_a_down_choice_with_no_channel_named_is_queued_again(box, monkeypatch):
    """Disarm: `connected_platforms` back to «up or None» → every link reported down reads unknown and the send
    is queued."""
    from widgets.mensajeria.outbound import targets
    real = targets.connected_platforms
    monkeypatch.setattr(targets, "connected_platforms", lambda db=None: real(db) or None)
    with pytest.raises(AssertionError):
        test_with_every_link_reported_and_none_connected_a_send_is_refused_and_nothing_is_queued(
            box, {"contact": "Rowan", "text": "hola"})


def test_disarmed_the_named_only_guard_queues_a_send_on_its_only_down_channel(box):
    """Disarm: the guard refuses only a channel he NAMED (`want and … want not in up`) → the contact whose only
    channel is down is queued again."""
    import importlib
    import shutil
    from pathlib import Path
    from widgets.mensajeria import outbound
    from widgets.mensajeria.outbound import targets
    src = Path(targets.__file__)
    orig = src.read_text(encoding="utf-8")
    line = 'if ch and up is not None and (down := str(ch.get("platform") or "").strip().lower()) not in up:'
    assert line in orig, "the disarm no longer matches targets.py"
    try:
        src.write_text(orig.replace(line, "if want and ch and up is not None and (down := want) not in up:"),
                       encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(targets)
        importlib.reload(outbound)       # the package re-exports `resolve_target` by name
        assert line not in Path(targets.__file__).read_text(encoding="utf-8")
        with pytest.raises(AssertionError):
            test_a_contact_whose_only_channel_is_down_is_refused_while_another_platform_is_up(box)
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(targets)
        importlib.reload(outbound)

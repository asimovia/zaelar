"""Every order a widget queues to a connector has a receipt, and the receipt is the end state (V2-919 M3).

Measured 2026-11-16: `mensajeria:create_group` declared `done_when_unreadable` («the connector reports the creation
itself»), so a task holding it could never close checkpoint 1 — a `message` needs a readable end state before anything
leaves — and the row ended `cannot` over a call the widget and the connector carried out in 4 s. The receipt mechanism
already existed for sends (`sent.outbox_open` on the order, `outbox_settle` on the connector's echo); now:

  · the group order opens its outbox row by its `ref`, named by the group;
  · the connector's success (the new group's chat row carrying the order's `ref`) settles it `sent`, its failure
    (`msg.send_failed`) settles it `failed` with the reason — through the owner, the one writer of the card's store;
    both connectors' drains are exercised with a client double, and a bridge that returns no group id is a failure;
  · the action's end state is that row: met by the success only, never by the queue nor by the failure;
  · with a readable end state the retained act crosses the exit door and reaches the widget's door: checkpoint 1 is
    closed by the rule that already exists, not relaxed (a `message` with no end state is still refused);
  · invariant: every leaving action declares `done_when`, or a `done_when_unreadable` that does not claim the
    connector reports it.

Disarmed (seen red): `outbox_open` dropped from the group order → no row; the `ref` dropped from the owner's settle
→ the row stays queued and the end state is never met.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, embeddings as mememb
from nucleo.circuit import spec, verify


@pytest.fixture
def card(tmp_path, monkeypatch):
    """The messaging card's store in a temp dir; members resolve without a directory (the card's own refusal is
    exercised elsewhere)."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.mensajeria import data as md
    from widgets.mensajeria.actions import groups
    monkeypatch.setattr(groups, "_by_id", lambda members, payload: list(members))
    monkeypatch.setattr(md._outbound, "resolve_target",
                        lambda p: {"ok": True, "to": "34600", "chatId": "34600@s.whatsapp.net",
                                   "name": str(p.get("contact")), "contactId": "c1"})
    yield md
    spec.reset()
    memdb.reset_db()
    mememb.reset()


def _outbox(md) -> list[dict]:
    return [r for r in (md.load_db().get("outbox") or []) if isinstance(r, dict)]


def _owner_applies(topic_attr: str, events: list[dict]) -> None:
    """The owner's real appliers over a drained batch (no bus, no thread)."""
    from widgets.mensajeria import owner
    o = owner._Owner.__new__(owner._Owner)
    o._chats_sub = o._failed_sub = object()
    o._drain = lambda sub: list(events)
    getattr(o, topic_attr)()


@pytest.mark.parametrize("name", ["Cena", "Trip"])
def test_the_group_order_opens_its_receipt_and_the_echo_settles_it_sent(card, name):
    md = card
    got = md.apply_action("create_group", {"platform": "whatsapp", "name": name, "members": ["Ana Prat"]})
    assert got["ok"], got
    ref = got["result"]["ref"]
    rows = [r for r in _outbox(md) if r["ref"] == ref]
    assert len(rows) == 1 and rows[0]["state"] == "queued" and rows[0]["name"] == name
    dw = spec.render("mensajeria", "create_group", {"platform": "whatsapp", "name": name, "members": ["Ana Prat"]})
    assert dw and verify.check(dw) is False, "the order in the queue is not the group created"
    _owner_applies("_apply_chats", [{"platform": "whatsapp", "chats": [
        {"chatId": "120363@g.us", "name": name, "kind": "group", "ref": ref}]}])
    assert [r["state"] for r in _outbox(md) if r["ref"] == ref] == ["sent"]
    assert verify.check(dw) is True, "the connector's echo of OUR order is the end state"


def test_the_connectors_failure_settles_it_failed_with_the_reason_and_never_met(card):
    md = card
    got = md.apply_action("create_group", {"platform": "telegram", "name": "Viaje", "members": ["Ana Prat"]})
    ref = got["result"]["ref"]
    dw = spec.render("mensajeria", "create_group", {"platform": "telegram", "name": "Viaje", "members": ["Ana Prat"]})
    _owner_applies("_apply_send_failures", [{"platform": "telegram", "ref": ref, "name": "Viaje",
                                             "reason": "USER_PRIVACY_RESTRICTED"}])
    row = next(r for r in _outbox(md) if r["ref"] == ref)
    assert (row["state"], row["reason"]) == ("failed", "USER_PRIVACY_RESTRICTED")
    assert verify.check(dw) is False
    _owner_applies("_apply_chats", [{"platform": "telegram", "chats": [{"chatId": "-100", "name": "Viaje",
                                                                         "kind": "group", "ref": ref}]}])
    assert verify.check(dw) is False, "a late echo never turns a failure into a success"


def test_a_chat_row_with_no_order_settles_nothing(card):
    md = card
    got = md.apply_action("create_group", {"platform": "whatsapp", "name": "Cena", "members": ["Ana Prat"]})
    _owner_applies("_apply_chats", [{"platform": "whatsapp", "chats": [{"chatId": "x@g.us", "name": "Cena"}]}])
    assert [r["state"] for r in _outbox(card) if r["ref"] == got["result"]["ref"]] == ["queued"]


class _Inbox:
    def __init__(self, orders):
        self.orders = list(orders)

    def drain(self):
        out, self.orders = self.orders, []
        return out


def _echoes(monkeypatch):
    from connectors.messaging import ingest
    got = {"chats": [], "failed": []}
    monkeypatch.setattr(ingest, "publish_chats", lambda platform, chats, **kw: got["chats"].extend(chats))
    monkeypatch.setattr(ingest, "publish_send_failed", lambda order, reason: got["failed"].append((order["ref"], reason)))
    return got


ORDER = {"platform": "x", "ref": "ref-7", "name": "Viaje", "members": [{"to": "34600", "chatId": "34600@s.whatsapp.net"}],
         "text": "", "attachments": []}


@pytest.mark.parametrize("gid,ok", [("120363@g.us", True), ("", False)])
def test_whatsapp_echoes_the_orders_ref_and_no_group_id_is_a_failure(monkeypatch, gid, ok):
    from connectors.whatsapp import client
    from connectors.whatsapp import service as wa
    from connectors.whatsapp.service import directory
    got = _echoes(monkeypatch)
    monkeypatch.setattr(wa, "_group_inbox", _Inbox([dict(ORDER)]))
    monkeypatch.setattr(wa, "_note", lambda *a, **k: None)

    async def _create(name, members):
        return {"id": gid}
    monkeypatch.setattr(client, "create_group", _create)
    asyncio.run(directory._drain_groups())
    if ok:
        assert [c.get("ref") for c in got["chats"]] == ["ref-7"] and got["failed"] == []
    else:
        assert got["chats"] == [] and [r for r, _w in got["failed"]] == ["ref-7"], "no group id back is no group"


@pytest.mark.parametrize("fails", [False, True])
def test_telegram_echoes_the_orders_ref_or_its_failure(monkeypatch, fails):
    import telethon.utils
    from connectors.telegram import service as tg
    got = _echoes(monkeypatch)
    monkeypatch.setattr(tg, "_group_inbox", _Inbox([dict(ORDER, members=[{"to": "@ana", "chatId": ""}])]))
    monkeypatch.setattr(tg, "_note", lambda *a, **k: None)
    monkeypatch.setattr(telethon.utils, "get_peer_id", lambda ch: -100123)

    class _Client:
        async def __call__(self, req):
            if fails:
                raise RuntimeError("USER_PRIVACY_RESTRICTED")
            return type("R", (), {"chats": [object()]})()

        async def get_input_entity(self, ref):
            return ref
    monkeypatch.setattr(tg, "_client", _Client())
    asyncio.run(tg._drain_groups())
    if fails:
        assert got["chats"] == [] and [r for r, _w in got["failed"]] == ["ref-7"]
    else:
        assert [c.get("ref") for c in got["chats"]] == ["ref-7"] and got["failed"] == []


def test_every_leaving_action_declares_a_readable_end_state_or_why_not():
    from widgets import effects, runtime
    for w in runtime.catalog():
        wid = str(w.get("id") or "")
        for act, s in ((runtime.get(wid) or {}).get("actions") or {}).items():
            if not (isinstance(s, dict) and effects.leaves(wid, act)):
                continue
            why = str(s.get("done_when_unreadable") or "")
            assert s.get("done_when") or why, (wid, act)
            assert "connector reports" not in why.lower(), (wid, act, "the connector's report IS a readable receipt")


def test_the_retained_group_crosses_the_exit_door_by_its_end_state(card, monkeypatch):
    """Checkpoint 1 is closed by the row's readable end state — and is NOT relaxed: the same row without one is
    refused, as before."""
    from nucleo import his_words, untrusted
    from nucleo.circuit import spec as _spec
    from nucleo.flash import data_ops
    from nucleo.request import model, send_task, send_task_run
    from nucleo.workers.prompts import playbook
    untrusted.reset()
    his_words.reset()
    reached = []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        reached.append((wid, action, dict(payload), row))
        return {"ok": True}
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    said = "make a WhatsApp group with Ana Prat called Dinner"
    model.begin(said, trace="t-1")
    his_words.note(said)
    reading = {"result": {"message_channel": {"choice": "whatsapp", "confidence": 0.97}}, "open_ids": ["mensajeria"]}
    payload = {"name": "Dinner", "platform": "whatsapp", "members": ["Ana Prat"]}
    uid = send_task.retain("mensajeria", "create_group", payload, said, reading=reading)
    assert uid and (_spec.of_task(uid) or {}).get("done_when"), "the row is born with the order's receipt"
    res = asyncio.run(send_task_run.run(uid))
    assert res.get("ok") is not False and reached == [("mensajeria", "create_group", payload, uid)], res
    from types import SimpleNamespace
    assert playbook.checkpoint_one(SimpleNamespace(playbook_chosen="message", done_when={}, task_id="", uid="")), \
        "a message with no end state still cannot leave"
    model._TURN.set(None)
    untrusted.reset()
    his_words.reset()


@pytest.mark.parametrize("act,payload", [("send_to", {"contact": "Rowan", "text": "hi"}),
                                         ("forward", {"contact": "Rowan", "text": "fyi", "from": "Ana"}),
                                         ("send_draft", {"contact": "Rowan"})])
def test_a_group_row_and_a_send_row_never_answer_for_each_other(card, act, payload):
    """The receipt names its class: a group called like a person never settles that person's send, and her send never
    settles a group of her name (the class is declared by whoever opens the row, never inferred)."""
    md = card
    from widgets.mensajeria import sent as _sent
    send_dw = spec.render("mensajeria", act, payload)
    group_dw = spec.render("mensajeria", "create_group", {"platform": "whatsapp", "name": "Rowan", "members": ["Ana"]})
    ref = md.apply_action("create_group", {"platform": "whatsapp", "name": "Rowan", "members": ["Ana Prat"]})["result"]["ref"]
    _owner_applies("_apply_chats", [{"platform": "whatsapp", "chats": [{"chatId": "g@g.us", "name": "Rowan", "ref": ref}]}])
    assert verify.check(group_dw) is True
    assert verify.check(send_dw) is False, "the group's receipt is not a message to Rowan"
    db = md.load_db()
    _sent.outbox_queue(db, "ref-send", "whatsapp", "34600@s.whatsapp.net", "", "hi", name="Rowan")
    _sent.outbox_settle(db, "ref-send", True)
    md.store.save(md.WIDGET_ID, db)
    assert verify.check(send_dw) is True
    group_dw2 = spec.render("mensajeria", "create_group", {"platform": "whatsapp", "name": "Rowan", "members": ["Ana"]})
    assert verify.check(group_dw2) is False, "her message is not a new group of her name"

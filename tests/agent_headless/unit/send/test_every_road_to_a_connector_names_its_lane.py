"""Every road that can make a message leave names its LANE, and the hold switch stops each one where it would queue.

The messaging card queues an order; its owner flushes the queue through the one exit door (`connectors/exit.py`).
Held here, with nothing ever sent for real (the bus is listened to, no connector runs):
  · each road — the message owner, his hand on the card, a worker's act, an errand's reply, the autoresponder —
    queues an order carrying ITS lane, and the flush publishes it;
  · an act with no lane, or with a lane a MODEL wrote into its payload, queues nothing and answers «not sent»;
  · with the switch on, every lane is refused before it queues, the owner says so BEFORE asking for his yes, and an
    order that was already waiting in the queue is held at the flush and answered as failed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import bus
import pytest

from connectors import exit as door
from connectors.messaging import group_leave, ingest

_CHAT = {"platform": "whatsapp", "chatId": "34600000001@s.whatsapp.net"}
_OUT = (ingest.TOPIC_SEND, ingest.TOPIC_REPLY, ingest.TOPIC_GROUP, group_leave.TOPIC_GROUP_LEAVE)


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv(door.ENV, raising=False)
    door._reset_counters()
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["platforms"]["whatsapp"] = {"status": "connected"}
    db["active_chat"] = dict(_CHAT)
    store.save("mensajeria", db)
    return md


@pytest.fixture
def wire():
    """What reached the bus: `wire("msg.reply")` drains that topic."""
    subs = {t: bus.subscribe(t) for t in (*_OUT, ingest.TOPIC_SEND_FAILED)}

    def seen(topic):
        got = []
        while True:
            try:
                got.append(subs[topic].queue.get_nowait())
            except Exception:  # noqa: BLE001 — empty
                return got
    yield seen
    for s in subs.values():
        s.close()


def _flush():
    from widgets.mensajeria.owner.handle import _Handle
    _Handle()._flush_queues()


def _queued(box) -> list[dict]:
    db = box.load_db()
    return [*db.get("pending_send", []), *db.get("pending_reply", []), *db.get("pending_group", []),
            *db.get("pending_group_leave", [])]


def _reply(lane=None, text="On my way"):
    return {"text": text, **({"_lane": lane} if lane is not None else {})}


def _card(**over):
    return {"chat": dict(_CHAT), "ref": "c-1", "box_key": "c:whatsapp:" + _CHAT["chatId"], "text": "Ten minutes", **over}


# ── each road queues with its own lane, and the flush publishes it ─────────────────────────────────────────────────

@pytest.mark.parametrize("lane", [door.OWNER, door.HAND, door.WORKER, door.MANDATE])
def test_an_act_stamped_by_its_door_queues_with_that_lane_and_leaves(box, wire, lane):
    out = box.apply_action("reply", _reply(door.stamp(lane)))
    assert out.get("ok") is not False, out
    assert [o["lane"] for o in _queued(box)] == [lane]
    _flush()
    assert [(o["lane"], o["text"]) for o in wire(ingest.TOPIC_REPLY)] == [(lane, "On my way")]
    assert door.counters() == {f"reply/{lane}/out": 1}


def test_the_owner_stamps_its_own_lane_on_the_act_it_runs():
    from nucleo.send import deliver
    d = SimpleNamespace(extra={}, target={"name": "Odile", "contact_id": "c2", "platform": "whatsapp"}, who="Odile",
                        channel="", text="hello")
    lane = deliver.payload(d)["_lane"]
    assert lane == door.OWNER and isinstance(lane, door.Stamp)


def test_his_click_reaches_the_card_as_his_hand_through_the_whole_route(box, wire):
    """The stamp survives the route a button takes: the HTTP door, the contract's folds, the card's action."""
    from widgets import server_api
    asyncio.run(server_api.widget_action("mensajeria", {"action": "send_draft", "payload": _card()}))
    assert [o["lane"] for o in _queued(box)] == [door.HAND]


def test_an_errands_reply_is_queued_on_the_errand_lane(box, wire):
    from nucleo.errands import wake
    assert wake._send({"id": "e1"}, "telegram", "987", "Six works for me.", "Rowan") is True
    assert [o["lane"] for o in _queued(box)] == [door.ERRAND]


# ── a road nobody declared cannot send ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lane", [None, "hand", "owner", "", 7])
def test_an_act_with_no_stamp_queues_nothing_and_says_not_sent(box, wire, lane):
    """No lane, or the right letters written by something that is not our door (a model's payload): held."""
    out = box.apply_action("reply", _reply(lane))
    assert out["ok"] is False and out["error"] == "held" and out["held"] == "held:unlabelled" and out["message"]
    assert _queued(box) == []
    _flush()
    assert all(wire(t) == [] for t in _OUT)


def test_a_models_call_through_the_brain_door_is_not_his_hand(box, wire):
    from widgets import server_api
    asyncio.run(server_api.brain_action("mensajeria", "reply", {"text": "hi", "_lane": "hand"}))
    assert _queued(box) == []


def test_an_order_already_in_the_queue_with_no_lane_is_held_at_the_flush(box, wire):
    db = box.load_db()
    db.setdefault("pending_send", []).append({"ref": "old-1", "platform": "telegram", "to": "987", "chatId": "987",
                                              "text": "queued by an older build"})
    box.store.save("mensajeria", db)
    _flush()
    assert wire(ingest.TOPIC_SEND) == []
    assert [(f["ref"], f["reason"]) for f in wire(ingest.TOPIC_SEND_FAILED)] == [("old-1", "held:unlabelled")]


# ── the switch ─────────────────────────────────────────────────────────────────────────────────────────────────────

LANES = [door.OWNER, door.HAND, door.WORKER, door.MANDATE, door.ERRAND, door.AUTORESPOND, door.INVITE]


@pytest.mark.parametrize("lane", LANES)
def test_with_the_switch_on_no_lane_queues_an_order(box, wire, monkeypatch, lane):
    from widgets.mensajeria import outbound
    monkeypatch.setenv(door.ENV, "all")
    db = box.load_db()
    with pytest.raises(outbound.Held) as held:
        outbound.enqueue(db, {"platform": "telegram", "to": "987", "chatId": "987"}, "hello", lane=lane)
    assert held.value.why == "held:switch"
    with pytest.raises(outbound.Held):
        outbound.enqueue_reply(db, dict(_CHAT), "hello", lane=lane)
    assert not db.get("pending_send") and not db.get("pending_reply") and not db.get("outbox")
    assert door.counters() == {f"send/{lane}/held": 1, f"reply/{lane}/held": 1}


@pytest.mark.parametrize("lane", LANES)
def test_an_order_queued_before_the_switch_is_held_at_the_flush_and_answered_failed(box, wire, monkeypatch, lane):
    from widgets.mensajeria import outbound
    db = box.load_db()
    order = outbound.enqueue(db, {"platform": "telegram", "to": "987", "chatId": "987"}, "hello", lane=lane)
    box.store.save("mensajeria", db)
    monkeypatch.setenv(door.ENV, lane)                 # only this lane is named
    _flush()
    assert wire(ingest.TOPIC_SEND) == []
    assert [(f["ref"], f["reason"]) for f in wire(ingest.TOPIC_SEND_FAILED)] == [(order["ref"], f"held:lane:{lane}")]


def test_the_owner_says_it_before_asking_for_his_yes(box, monkeypatch):
    from nucleo.send import deliver
    d = SimpleNamespace(extra={}, target={"name": "Odile", "contact_id": "c2", "platform": "whatsapp"}, who="Odile",
                        channel="", text="hello")
    monkeypatch.setenv(door.ENV, "owner")
    got = deliver.check(d)
    assert got["ok"] is False and got["held"] is True and "paused" in got["why"]
    assert door.counters() == {}, "a question is not an exit: nothing is counted until an act is refused"


def test_his_own_send_is_refused_at_the_button_and_its_row_says_why(box, wire, monkeypatch):
    monkeypatch.setenv(door.ENV, "all")
    payload = {**_card(), "_lane": door.stamp(door.HAND)}
    veto = box.answer_action("reply", _reply(door.stamp(door.HAND)))     # an act that always sends: vetoed up front
    assert veto and veto["ok"] is False and veto["error"] == "held"
    res = box.apply_action("send_draft", payload)
    assert res["ok"] is False and res["error"] == "held" and not box.load_db().get("pending_reply")
    row = box.load_db()["outbox"][-1]
    assert row["state"] == "failed" and row.get("reason"), "the card's row says it did not leave"


def test_an_errand_and_a_group_are_refused_too(box, wire, monkeypatch):
    from nucleo.errands import wake
    monkeypatch.setenv(door.ENV, "all")
    assert wake._send({"id": "e1"}, "telegram", "987", "Six works for me.", "Rowan") is False
    out = box.apply_action("leave_group", {"group": "Nobody's group", "_lane": door.stamp(door.WORKER)})
    assert out["ok"] is False
    assert _queued(box) == []


def test_the_autoresponder_answers_nobody_while_its_lane_is_held(box, wire, monkeypatch):
    from widgets.mensajeria import autorespond
    from widgets.mensajeria.owner import apply as _apply
    from nucleo import consent
    monkeypatch.setattr(autorespond, "config_for", lambda db, platform: {"enabled": True})
    monkeypatch.setattr(autorespond, "should_reply", lambda *a, **k: "I am away until Monday.")
    monkeypatch.setattr(autorespond, "note_replied", lambda *a, **k: None)
    monkeypatch.setattr(_apply, "_owned_elsewhere", lambda platform, item: "")
    monkeypatch.setattr(consent, "decide_act", lambda *a, **k: {"verdict": consent.RUN})
    item = {"chatId": "987", "senderId": "987", "messageId": "m1"}
    assert _apply._Apply()._auto_reply("telegram", [item]) == 1
    assert [o["lane"] for o in wire(ingest.TOPIC_REPLY)] == [door.AUTORESPOND]
    monkeypatch.setenv(door.ENV, "autorespond")
    assert _apply._Apply()._auto_reply("telegram", [item]) == 0
    assert wire(ingest.TOPIC_REPLY) == []
    assert door.counters() == {"reply/autorespond/out": 1, "reply/autorespond/held": 1}

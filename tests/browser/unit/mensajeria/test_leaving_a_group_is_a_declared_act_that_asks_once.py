"""Leaving a group is a declared act of the messaging card, and it asks once.

Measured on the operator's engine (2026-11-18): «delete the groups X and "Shopping list"» had no act to land on — the
engine picked `dismiss`, which only hides a row here, ran for six minutes and finished nothing. `leave_group` is the
act: every name is found among HIS group chats before anything is ordered (one missing or ambiguous name and nothing
runs), the exit door asks once naming the groups as found, and the order's one outbox row settles sent only when
every chat is gone — a partial failure settles it failed, naming the one that stayed.
"""
from __future__ import annotations

import queue

import pytest

WA_BOOK = "120363600112233@g.us"
WA_BOOK_ARCHIVE = "120363915550000@g.us"
WA_BIRTHDAY = "120363600000020@g.us"
TG_SHOPPING = "-100600000311"


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["chat_index"] = {
        "whatsapp": {"rows": {
            WA_BOOK: {"chatId": WA_BOOK, "name": "Book club", "kind": "group", "ts": 3},
            WA_BOOK_ARCHIVE: {"chatId": WA_BOOK_ARCHIVE, "name": "Book club archive", "kind": "group", "ts": 2},
            WA_BIRTHDAY: {"chatId": WA_BIRTHDAY, "name": "Cumpleaños de Quinn", "kind": "group", "ts": 1},
            "600112233@s.whatsapp.net": {"chatId": "600112233@s.whatsapp.net", "name": "Quinn Ferrer",
                                         "kind": "person", "ts": 4}}},
        "telegram": {"rows": {TG_SHOPPING: {"chatId": TG_SHOPPING, "name": "Shopping list", "kind": "group", "ts": 5}}},
    }
    db["threads"] = {f"whatsapp|{WA_BOOK}": {"name": "Book club", "isGroup": True,
                                             "msgs": [{"id": "m1", "dir": "in", "body": "hola", "ts": 3}]}}
    db["items"] = [{"platform": "whatsapp", "chatId": WA_BOOK, "messageId": "m1", "body": "hola", "ts": 3}]
    md.store.save(md.WIDGET_ID, db)
    return md


def _row(md, ref):
    return next(r for r in md.load_db()["outbox"] if r["ref"] == ref)


class _Sub:
    def __init__(self, *events):
        self.queue = queue.Queue()
        for e in events:
            self.queue.put(e)


def _owner(gone=(), failed=()):
    from widgets.mensajeria import owner
    o = owner._Owner()
    o._gone_sub, o._failed_sub = _Sub(*gone), _Sub(*failed)
    return o


# ── the declaration ─────────────────────────────────────────────────────────────────────────────────────────────

def test_leaving_a_group_is_declared_as_an_act_that_leaves_and_asks_by_its_event_type():
    from nucleo.events import vocabulary
    from nucleo.workers import exit_gate, exit_risk
    from widgets import runtime
    spec = runtime.get("mensajeria")["actions"]["leave_group"]
    assert spec["consent_class"] == "messaging.leave_group" and "external.send" in spec["effects"]
    assert spec["types"] == {"groups": "list"} and "{groups}" in spec["confirm_q"] and spec["confirm"] is False
    assert len(spec["desc"]) <= 200
    assert spec["done_when"]["where"]["kind"] == "group_leave"
    t = vocabulary.of("messaging.leave_group")
    assert t and t.direction == vocabulary.OUT and t.grant == "message" and t.effect == "external.send"
    assert exit_gate.leaves("mensajeria", "leave_group")
    assert exit_risk.asks_by_itself("mensajeria", "leave_group", {"groups": ["Book club"]})


def test_the_genesis_default_for_leaving_a_group_is_ask():
    import json
    import pathlib
    g = json.loads((pathlib.Path(__file__).parents[4] / "nucleo" / "genesis.json").read_text())
    assert g["consent"]["classes"]["messaging.leave_group"] == "ask"


def test_dismiss_says_it_only_hides_and_points_to_leave_group():
    from widgets import runtime
    spec = runtime.get("mensajeria")["actions"]["dismiss"]
    assert "nunca sale ni borra un grupo" in spec["desc"] and len(spec["desc"]) <= 200
    assert "leave_group" in spec["how"]


def test_disarmed_a_standard_level_would_run_it_without_asking(monkeypatch):
    from nucleo.events import vocabulary
    from nucleo.workers import exit_risk
    t = vocabulary.of("messaging.leave_group")
    monkeypatch.setitem(vocabulary._BY_NAME, "messaging.leave_group", t._replace(level="standard"))
    from nucleo import consent
    monkeypatch.setattr(consent, "class_policy", lambda cls: "allow")
    assert not exit_risk.asks_by_itself("mensajeria", "leave_group", {"groups": ["Book club"]})


# ── resolution ──────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("said, want", [
    ("Book club", ["Book club"]),                              # exact wins over «Book club archive»
    ("book CLUB archive", ["Book club archive"]),
    ("cumpleanos de quinn", ["Cumpleaños de Quinn"]),          # accents and case aside
    ("Book club y «Shopping list»", ["Book club", "Shopping list"]),
    (["Shopping list", "Cumpleaños"], ["Shopping list", "Cumpleaños de Quinn"]),   # a partial that is unique
])
def test_each_name_resolves_to_one_of_his_groups(box, said, want):
    from widgets.mensajeria.actions import leave
    found, no = leave.resolve(box.load_db(), {"groups": said})
    assert no is None, no
    assert [r["name"] for r in found] == want


def test_disarmed_without_the_exact_preference_book_club_is_ambiguous(box, monkeypatch):
    from widgets.mensajeria.actions import leave
    monkeypatch.setattr(leave, "_match", lambda pool, said: [r for r in pool if leave._norm(said) in leave._norm(r["name"])])
    found, no = leave.resolve(box.load_db(), {"groups": "Book club"})
    assert no and "varios" in no["error"]


@pytest.mark.parametrize("said, why", [("Book club y Hiking", "no está"), ("Book", "varios"), ("Quinn Ferrer", "no está")])
def test_a_missing_or_ambiguous_name_refuses_before_anything_is_queued_or_asked(box, said, why):
    from widgets import contract
    r = box.apply_action("leave_group", {"groups": said})
    assert r["ok"] is False and r["missing"] == "groups" and why in r["error"]
    assert not box.load_db().get("pending_group_leave") and not box.load_db().get("outbox")
    no = contract.would_refuse("mensajeria", "leave_group", {"groups": said})
    assert no and no["missing"] == "groups" and why in no["error"]
    if why == "varios":
        assert any("Book club archive" in c for c in no["candidates"]["Book"])


def test_disarmed_without_its_dry_check_the_door_would_ask_about_a_group_that_is_not_there(box, monkeypatch):
    from widgets import contract
    from widgets.mensajeria.actions import leave
    monkeypatch.setattr(leave, "refusal", lambda payload: None)
    assert contract.would_refuse("mensajeria", "leave_group", {"groups": "Hiking"}) is None


def test_the_question_names_the_groups_as_found_not_his_words(box):
    from nucleo.workers import exit_risk
    q = exit_risk.ready_question("mensajeria", "leave_group", {"groups": "book club y shopping list"})
    assert "«Book club»" in q and "«Shopping list»" in q and "shopping list" not in q


def test_disarmed_without_the_cards_values_the_question_repeats_his_raw_words(box, monkeypatch):
    from nucleo.workers import exit_risk
    from widgets.mensajeria import data as md
    monkeypatch.setattr(md, "confirm_values", lambda action, payload: {})
    q = exit_risk.own_question("mensajeria", "leave_group", {"groups": "book club y shopping list"})
    assert "book club y shopping list" in q and "«Book club»" not in q


# ── the order and its receipt ───────────────────────────────────────────────────────────────────────────────────

def test_two_groups_on_two_platforms_are_one_outbox_row_and_one_order_per_platform(box):
    r = box.apply_action("leave_group", {"groups": ["Book club", "Shopping list"]})
    assert r["ok"], r
    assert r["result"]["groups"] == ["Book club", "Shopping list"]
    db = box.load_db()
    rows = [x for x in db["outbox"] if x.get("kind") == "group_leave"]
    assert len(rows) == 1 and rows[0]["state"] == "queued" and rows[0]["name"] == "Book club, Shopping list"
    orders = {o["platform"]: o for o in db["pending_group_leave"]}
    assert set(orders) == {"whatsapp", "telegram"} and {o["ref"] for o in orders.values()} == {r["result"]["ref"]}
    assert orders["whatsapp"]["chats"] == [{"chatId": WA_BOOK, "name": "Book club"}]
    assert orders["telegram"]["chats"] == [{"chatId": TG_SHOPPING, "name": "Shopping list"}]
    from connectors.messaging import store as msgstore
    assert len(msgstore.take_pending_group_leave()) == 2 and not msgstore.take_pending_group_leave()


def test_the_gone_echo_removes_the_chats_and_settles_the_row_only_when_every_chat_left(box):
    ref = box.apply_action("leave_group", {"groups": ["Book club", "Shopping list"]})["result"]["ref"]
    _owner(gone=[{"platform": "whatsapp", "ref": ref, "chatIds": [WA_BOOK]}])._apply_chats_gone()
    db = box.load_db()
    assert WA_BOOK not in db["chat_index"]["whatsapp"]["rows"] and f"whatsapp|{WA_BOOK}" not in db["threads"]
    assert not [it for it in db["items"] if it["chatId"] == WA_BOOK]
    assert _row(box, ref)["state"] == "queued", "Shopping list has not left yet"
    _owner(gone=[{"platform": "telegram", "ref": ref, "chatIds": [TG_SHOPPING]}])._apply_chats_gone()
    assert _row(box, ref)["state"] == "sent"
    assert TG_SHOPPING not in box.load_db()["chat_index"]["telegram"]["rows"]


def test_disarmed_without_the_wait_list_the_first_echo_settles_the_whole_order(box, monkeypatch):
    from widgets.mensajeria import sent
    monkeypatch.setattr(sent, "outbox_wait", lambda db, ref, keys: None)
    ref = box.apply_action("leave_group", {"groups": ["Book club", "Shopping list"]})["result"]["ref"]
    _owner(gone=[{"platform": "whatsapp", "ref": ref, "chatIds": [WA_BOOK]}])._apply_chats_gone()
    assert _row(box, ref)["state"] == "sent"


def test_a_partial_failure_settles_the_row_failed_naming_the_group_that_stayed(box, monkeypatch):
    from widgets.mensajeria import owner
    monkeypatch.setattr(owner, "_note", lambda text: None)
    ref = box.apply_action("leave_group", {"groups": ["Book club", "Shopping list"]})["result"]["ref"]
    o = _owner(gone=[{"platform": "whatsapp", "ref": ref, "chatIds": [WA_BOOK]}],
               failed=[{"platform": "telegram", "ref": ref, "reason": "no pude salir de «Shopping list»: flood wait"}])
    o._apply_send_failures()
    o._apply_chats_gone()
    row = _row(box, ref)
    assert row["state"] == "failed" and "Shopping list" in row["reason"]
    assert WA_BOOK not in box.load_db()["chat_index"]["whatsapp"]["rows"], "the group that left is gone all the same"
    assert TG_SHOPPING in box.load_db()["chat_index"]["telegram"]["rows"]


def test_the_owner_flushes_the_queue_onto_its_own_topic(box, monkeypatch):
    from connectors.messaging import group_leave
    from widgets.mensajeria import owner
    sent_orders = []
    monkeypatch.setattr(group_leave, "publish_group_leave", lambda order: sent_orders.append(order))
    box.apply_action("leave_group", {"groups": "Book club"})
    owner._Owner()._flush_queues()
    assert [o["chats"] for o in sent_orders] == [[{"chatId": WA_BOOK, "name": "Book club"}]]
    assert not box.load_db().get("pending_group_leave")


def test_the_declared_end_state_renders_from_his_words_and_meets_the_settled_row(box):
    from nucleo.circuit import spec
    from widgets import rows
    said = "book club y shopping list"
    dw = spec.render("mensajeria", "leave_group", {"groups": said})
    assert dw and dw["where"] == {"said": said, "kind": "group_leave", "state": "sent"}
    assert spec.render("mensajeria", "leave_group", {"contact": "Quinn Ferrer"}) is None, \
        "a send's payload never renders a leave's end state"
    ref = box.apply_action("leave_group", {"groups": said})["result"]["ref"]
    assert not rows.matches(_row(box, ref), dw["where"])
    _owner(gone=[{"platform": "whatsapp", "ref": ref, "chatIds": [WA_BOOK]},
                 {"platform": "telegram", "ref": ref, "chatIds": [TG_SHOPPING]}])._apply_chats_gone()
    assert rows.matches(_row(box, ref), dw["where"])

"""«Delete the groups X and "Shopping list"», replayed end to end through the real card (V2-935).

What he lived (2026-11-18, 11:19–11:26): no act existed that leaves or deletes a messaging group; the turn's reader
took the nearest one (`dismiss`, which only hides a row here), a generic worker spent six minutes on it, asked him
nothing, verified nothing and never ended. Each station of the path, now:

  · the turn: a sure order whose act LEAVES is handed to ONE worker task with the act's own steps and fields in its
    brief — never a card act run inline, never a generic errand that has to discover how;
  · the exit door: every name is found among HIS groups before anything is asked (a group that is not there is a
    refusal with the candidates, and no question); then ONE question for all of them, naming them as found;
  · his yes: the retained act runs at once — no session resumed — and he hears the one «on it» line of an act
    (never «the message»); the order is queued for each platform's connector;
  · the receipt: only when every chat is gone does the order's row say sent; the engine then says the final line and
    the task's row ends done. Nothing is claimed before it.

The connectors are doubled at the bus (their echo is applied as the card's owner applies it); invented names.
"""
from __future__ import annotations

import asyncio
import json
import queue
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts

UID = "g9-2"
ORDER = "there is a group called Book club and another called Shopping list, delete them"
WA_BOOK, TG_SHOPPING = "120363600112233@g.us", "-100600000311"
CALL = {"widget_id": "mensajeria", "action": "leave_group", "payload": {"groups": ["Book club", "Shopping list"]}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent, dispatch, his_words, untrusted
    from nucleo.circuit import verify
    from nucleo.cli import worker_api, worker_api_answer, worker_api_resume
    from nucleo.pulse import notices
    from nucleo.request import send_receipt
    from nucleo.switchboard import route
    from nucleo.workers.prompts import playbook
    from widgets import server_api, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    untrusted.reset()
    his_words.reset()
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["chat_index"] = {
        "whatsapp": {"rows": {WA_BOOK: {"chatId": WA_BOOK, "name": "Book club", "kind": "group", "ts": 3}}},
        "telegram": {"rows": {TG_SHOPPING: {"chatId": TG_SHOPPING, "name": "Shopping list", "kind": "group", "ts": 5}}}}
    md.store.save(md.WIDGET_ID, db)
    worker_api._ACTS.clear()
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    w = SimpleNamespace(md=md, calls=[], resumed=[], events=[], spoken=[], lines=[], api=worker_api, kind="yes")

    async def _card(wid, act, payload):                          # the REAL card, on a store of its own
        w.calls.append((wid, act))
        return md.apply_action(act, dict(payload or {}))
    monkeypatch.setattr(server_api, "brain_action", _card)
    monkeypatch.setattr(verify, "card_view", lambda wid: md.view_data())
    monkeypatch.setattr(send_receipt, "POLL_S", 0.01)

    async def _notify(title, text, **kw):
        w.lines.append((kw.get("key", ""), text))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", _notify)
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: w.events.append(
        {"kind": kind, "label": label, "text": text, **(extra or {})}))
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e, src="answer": w.resumed.append(dict(e)) or 1)
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: None)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    now = int(time.time())
    ts.task_put({"id": UID, "goal": ORDER, "title": "Delete the groups «Book club» and «Shopping list»",
                 "state": "running", "playbook": "message", "created_at": now - 5, "started_at": now - 5})
    w.rec = SimpleNamespace(task_id="2", uid=UID, native_sid="sess-2", waiting_on="", ask="", ask_corr="", parked=False,
                            started=time.time(), depth=0, trace_id="", surface="", sheet="", mandate={},
                            playbook_chosen="message", parent_task_id="", kind="generic", goal=ORDER, heard=[ORDER],
                            own_words=True, reading=None)
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: w.rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: w.rec)
    monkeypatch.setattr(route, "ask_the_model", lambda text, procs, last="", before=None: (1, "double", w.kind))
    w.emit = lambda kind, label, text="", role="", extra=None: w.events.append({"kind": kind, "label": label, **(extra or {})})
    yield w
    worker_api._ACTS.clear()
    consent._reset_for_tests()
    memdb.reset_db()
    mememb.reset()


async def _act(w, action, payload=None):
    out = await w.api.worker_act(task_id="2", token="t", action=action, payload=payload or {})
    return json.loads(out.body)


def _asks(w) -> list:
    return [e for e in w.events if e["kind"] == "ask"]


def _gone(w, platform, chat_id, ref):
    """A connector's echo for one chat, applied as the card's owner applies it."""
    from widgets.mensajeria import owner
    o = owner._Owner()
    o._gone_sub, o._failed_sub = SimpleNamespace(queue=queue.Queue()), SimpleNamespace(queue=queue.Queue())
    o._gone_sub.queue.put({"platform": platform, "ref": ref, "chatIds": [chat_id]})
    o._apply_chats_gone()


def _order_row(w) -> dict:
    return next(r for r in w.md.load_db()["outbox"] if r.get("kind") == "group_leave")


# ── the turn ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_order_is_handed_to_one_worker_with_the_acts_own_steps(monkeypatch):
    """11:19:46 — the worker was started as a generic errand with `dismiss` as its first step. A sure order whose act
    leaves is the turn's ONE commission, on the playbook whose worker runs on the lead model, and its brief carries
    that act's declaration."""
    from nucleo.request import ask_outside_door, send_errand
    monkeypatch.setattr(ask_outside_door, "_sure_leaving_act", lambda brief: ("mensajeria", "leave_group"))
    esc = {"v": ORDER}
    send_errand.kept(esc, {}, brief=object(), calls=())
    assert esc["send"] == {"widget": "mensajeria", "action": "leave_group", "payload": {}, "text": ORDER}
    ctx = send_errand.context(esc)
    assert ctx["playbook"] == send_errand.PLAYBOOK
    brief = send_errand.brief_block(ctx)
    assert "mensajeria:leave_group" in brief and "groups" in brief and "draft" not in brief
    from widgets import effects
    assert effects.leaves("mensajeria", "leave_group") and not effects.leaves("mensajeria", "dismiss")


# ── the exit door, his yes, the receipt ─────────────────────────────────────────────────────────────────────────
def test_two_groups_are_found_asked_about_once_left_on_his_yes_and_verified(world):
    from i18n import langs
    from nucleo.switchboard import board, route
    lang = langs.current_language()

    async def session():
        got = await _act(world, "widget_data", CALL)
        assert got.get("status") == "pending", got
        (asked,) = _asks(world)
        assert "«Book club»" in asked["text"] and "«Shopping list»" in asked["text"], asked["text"]
        assert "cannot be undone" in asked["text"], "he is told what he is confirming"
        assert not world.md.load_db().get("pending_group_leave") and world.calls == [], "nothing ran before his yes"
        assert [(p["key"], p["state"]) for p in board.open_processes()] == [(UID, "waiting")]
        world.kind = "yes"
        assert await route.take("yes, delete both", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
        assert world.spoken == [lang.act_going], "the line of an act that leaves — never «the message»"
        assert world.calls == [("mensajeria", "leave_group")] and world.resumed == [], "run at once, no session resumed"
        orders = {o["platform"]: o["chats"] for o in world.md.load_db()["pending_group_leave"]}
        assert orders == {"whatsapp": [{"chatId": WA_BOOK, "name": "Book club"}],
                          "telegram": [{"chatId": TG_SHOPPING, "name": "Shopping list"}]}
        row = _order_row(world)
        assert row["state"] == "queued" and world.lines == [], "queued is not done: nothing is said yet"
        _gone(world, "whatsapp", WA_BOOK, row["ref"])
        await asyncio.sleep(0.05)
        assert _order_row(world)["state"] == "queued" and world.lines == [], "one of two left: still not done"
        assert ts.task_get(UID)["state"] != "done"
        _gone(world, "telegram", TG_SHOPPING, row["ref"])
        for _ in range(60):
            await asyncio.sleep(0.01)
            if world.lines:
                break
        assert [t for _k, t in world.lines] == [lang.act_done], world.lines
        assert ts.task_get(UID)["state"] == "done", "the row ends with the verdict the line says"
        db = world.md.load_db()
        assert WA_BOOK not in db["chat_index"]["whatsapp"]["rows"] and TG_SHOPPING not in db["chat_index"]["telegram"]["rows"]

    asyncio.run(session())
    assert len(_asks(world)) == 1, "ONE question for both groups"


@pytest.mark.parametrize("groups, names", [(["Book club", "Garden"], "Garden"), (["Chess"], "Chess")])
def test_a_group_that_is_not_his_is_refused_before_any_question(world, groups, names):
    async def session():
        got = await _act(world, "widget_data", {**CALL, "payload": {"groups": groups}})
        assert got.get("status") != "pending" and not _asks(world), got
        assert names in json.dumps(got, ensure_ascii=False), "the refusal names what was not found, so the worker asks him"
    asyncio.run(session())
    assert not world.md.load_db().get("pending_group_leave") and world.calls == []


def test_his_no_leaves_both_groups_where_they_are(world):
    from nucleo.switchboard import route

    async def session():
        await _act(world, "widget_data", CALL)
        world.kind = "no"
        assert await route.take("no, leave them", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
    asyncio.run(session())
    db = world.md.load_db()
    assert not db.get("pending_group_leave") and world.calls == [] and WA_BOOK in db["chat_index"]["whatsapp"]["rows"]


def test_disarm_declared_harmless_it_would_leave_without_asking(world, monkeypatch):
    """Two declarations make it ask — the event type's level and the class's factory rule; with both off it just runs."""
    from nucleo import consent
    from nucleo.events import vocabulary as voc
    t = voc.of("messaging.leave_group")
    monkeypatch.setitem(voc._BY_NAME, "messaging.leave_group", t._replace(level="standard"))
    monkeypatch.setattr(consent, "class_policy", lambda cls: "allow")

    async def session():
        got = await _act(world, "widget_data", CALL)
        assert got.get("status") != "pending" and world.calls == [("mensajeria", "leave_group")], got
    asyncio.run(session())


def test_an_end_state_reads_a_call_that_names_several_things():
    """The worker's call names the groups as a LIST; an end state whose blank is that field was unrenderable, so the
    act had no receipt to follow and nothing verified it. Several plain values are told as one, as the row keeps them."""
    from nucleo.circuit import spec
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": ["Book club", "Shopping list"]}) == \
        {"where": {"said": "Book club, Shopping list"}}
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": [{"name": "x"}]}) is None, "rows are not plain values"
    assert spec._fill({"where": {"said": "{groups}"}}, {"groups": []}) is None


def test_a_row_number_that_arrives_as_text_still_names_its_row(world):
    """11:23:24 — the worker's `dismiss n=2` arrived as the text "2" (its bridge passes fields as text), matched no
    row and was reported as done: nothing had been hidden either."""
    md = world.md
    db = md.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "a", "messageId": "m1", "body": "x", "ts": 3},
                   {"platform": "whatsapp", "chatId": "b", "messageId": "m2", "body": "y", "ts": 2}]
    md.store.save(md.WIDGET_ID, db)
    md.apply_action("dismiss", {"n": "2"})
    assert len(md.load_db()["items"]) == 1, "the row he numbered is the one that goes"

"""The voice turns of 2026-11-17 19:16–19:20, replayed through the new path: one task, one question, one send (V2-931).

What happened on his engine that evening, word for word in shape (the people are invented here):
  · «A ver, …, ¿me vas a mandar un mensaje a Quinn diciéndole que estamos en batería?» — the show guard read the bare
    «ver» and swapped the model's `send_to` for a show of the card;
  · one sentence of 28 s reached the engine as three turns; each opened its own send row and cancelled the last;
  · his yes arrived as two chunks — «Vale, mi respuesta es que sí…» and «Te doy mi permiso, mándalo.» — the binder
    read it at 0.04, the model re-called the send, and the second chunk alone was refused as «unbacked».
Nothing left.

Replayed here against the real doors — the turn's hand-off, the worker's bridge (`worker_act`), the exit door, the row
and its question, the switchboard, the answer door — with three doubles: the worker itself (a script that follows the
send's method), the routing model (the decisions it gave on these very chunks, measured live) and the connector.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts

ORDER = "A ver, Johnny, vamos a hacer una cosa ahora. ¿Me vas a mandar un mensaje a Quinn diciéndole que estamos en batería?"
TEXT = "estamos en batería"
YES_1 = "Vale, mi respuesta es que sí, ¿vale? pero precisamente al mensaje que me acabas de leer."
YES_2 = "Te doy mi permiso, mándalo."
UID = "b0-7"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import dispatch
    from nucleo.cli import worker_api, worker_api_answer, worker_api_resume
    from nucleo.switchboard import route
    from widgets import server_api
    from widgets.contactos import data as contacts
    worker_api._ACTS.clear()
    route._seen.update(text="", key="", at=0.0)
    w = SimpleNamespace(sent=[], asks=[], resumed=[], injects=[], events=[], spoken=[], api=worker_api)

    async def _connector(wid, act, payload):                    # the connector double: what really leaves
        w.sent.append((wid, act, dict(payload)))
        return {"ok": True, "queued": f"out-{len(w.sent)}"}
    monkeypatch.setattr(server_api, "brain_action", _connector)
    monkeypatch.setattr(contacts, "people_named", lambda q, limit=4: [
        {"name": "Quinn Ferrer", "channels": ["whatsapp"]}] if "quinn" in q.lower() else [])
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: w.events.append(
        {"kind": kind, "label": label, "text": text, **(extra or {})}))
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e, src="answer": w.resumed.append(dict(e)) or 1)
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: w.injects.append((which, words)))
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    now = int(time.time())
    ts.task_put({"id": UID, "goal": ORDER, "title": ORDER[:80], "state": "running", "playbook": "message",
                 "created_at": now - 5, "started_at": now - 5})
    w.rec = SimpleNamespace(task_id="7", uid=UID, native_sid="sess-1", waiting_on="", ask="", ask_corr="", parked=False,
                            started=time.time(), depth=0, trace_id="", surface="", sheet="", mandate={},
                            playbook_chosen="message", parent_task_id="", kind="generic", goal=ORDER)
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: w.rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: w.rec)
    monkeypatch.setattr(route, "ask_the_model", lambda text, procs, last="", before=None: (1, "confirms the send"))
    w.emit = lambda kind, label, text="", role="", extra=None: w.events.append({"kind": kind, "label": label, **(extra or {})})
    yield w
    worker_api._ACTS.clear()
    memdb.reset_db()
    mememb.reset()


async def _act(w, action, payload=None):
    out = await w.api.worker_act(task_id="7", token="t", action=action, payload=payload or {})
    return json.loads(out.body)


def _hand_over(text=ORDER) -> dict:
    """The turn: the model's `send_to` call on the «a ver» sentence, through the widget tool's own entry."""
    from nucleo.flash import tool_executor_widget_calls as calls
    esc = {"v": None, "surface": {}}
    events = []
    calls._handle_widget_data_tool(
        {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Quinn", "text": TEXT}},
        _apply_widget_data=lambda *a, **k: pytest.fail("a send never reaches the inline data door"),
        _brief=None, _frontend=SimpleNamespace(payload_ref=lambda *a, **k: ""), _identify=lambda *_a: "",
        _repeat_repair=None, _say=None, _tag_emit=lambda *a, **k: pytest.fail("a send is never swapped for a show"),
        acted={}, brain=None, clarify={}, deduped={"v": False},
        emit=lambda *a, **k: events.append((a, k)), escalate_req=esc, text=text)
    return esc


def test_the_a_ver_order_is_handed_to_one_worker_task_never_swapped_for_a_show():
    from nucleo.flash import show_guard
    from nucleo.request import send_errand
    assert show_guard.is_pure_show_request(ORDER), "the sentence still reads as a pure show to the guard…"
    esc = _hand_over()
    assert esc["v"] == ORDER and esc["leaves"] is True, "…and the send is the turn's commission all the same"
    assert esc["send"]["action"] == "send_to" and esc["send"]["payload"] == {"contact": "Quinn", "text": TEXT}
    ctx = send_errand.context(esc)
    assert ctx["playbook"] == "message", "the launch names the send's playbook: its worker runs on Claude"
    assert "find_contact" in send_errand.brief_block(ctx), "the worker's brief is the send's own method"


def test_one_task_one_question_the_yes_in_two_chunks_one_send_one_receipt(world):
    from nucleo.circuit import spec
    from nucleo.switchboard import board, route

    async def session():
        # 1 WHO — the worker finds the person in his contacts
        who = await _act(world, "find_contact", {"name": "Quinn"})
        assert [p["name"] for p in who["result"]["people"]] == ["Quinn Ferrer"]
        # 4 SEND — one call; the exit door asks his ONE confirmation and retains the act on the row
        call = {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Quinn Ferrer", "text": TEXT}}
        got = await _act(world, "widget_data", call)
        assert got.get("status") == "pending" and world.sent == [], got
        asked = [e for e in world.events if e["kind"] == "ask"]
        assert len(asked) == 1 and "Quinn Ferrer" in asked[0]["text"], asked
        procs = board.open_processes()
        assert [(p["key"], p["state"]) for p in procs] == [(UID, "waiting")], "the waiting send IS on the board"
        # 5 HIS ANSWER, first chunk — not a bare yes: it reaches the task as he said it, nothing runs yet
        assert await route.take(YES_1, emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
        assert world.sent == [], "a yes that is not one of the two declared answers is the worker's to read"
        assert len(world.resumed) == 1 and world.resumed[0]["answer"] == YES_1
        assert world.resumed[0]["result"] == {"ok": False, "unclear": True}
        # …the worker, resumed with his words, reads them as the confirmation and runs THE retained act
        ran = await _act(world, "confirm_send")
        assert ran.get("ok") is True, ran
        assert [(s[0], s[1], s[2]["contact"], s[2]["text"]) for s in world.sent] == [
            ("mensajeria", "send_to", "Quinn Ferrer", TEXT)]
        again = await _act(world, "confirm_send")
        assert again.get("ok") is False and len(world.sent) == 1, "the same yes never sends twice"
        # the second chunk of his yes: no question waits any more — it is no new send, no second row
        assert await route.take(YES_2, emit=world.emit, say=world.spoken.append) is False
        assert len(world.sent) == 1 and len([e for e in world.events if e["kind"] == "ask"]) == 1
        # 6 VERIFY — the end state the send declared is on the row for `bridge act verify`
        dw = (spec.of_task(UID) or {}).get("done_when")
        assert dw, "the send's declared end state (its outbox row) is recorded on the task"
        return await _act(world, "verify")

    verdict = asyncio.run(session())
    assert verdict.get("ok") is True and "met" in verdict["result"]
    routed = [e for e in world.events if e.get("event") == "switchboard"]
    assert [(e["to"], e["by"], e["delivered"]) for e in routed] == [(UID, "model", True)]


def test_a_bare_yes_runs_it_at_once_with_no_model(world):
    async def one(reply):
        call = {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Quinn Ferrer", "text": TEXT}}
        await _act(world, "widget_data", call)
        from nucleo.switchboard import route
        assert await route.take(reply, emit=world.emit) is True
        await asyncio.sleep(0.05)
    asyncio.run(one("Yes."))
    assert len(world.sent) == 1 and world.resumed[-1]["result"]["ok"] is True
    last = [e for e in world.events if e.get("event") == "switchboard"][-1]
    assert last["by"] == "declared", "the declared answer needs no model"


def test_disarmed_the_old_order_lets_the_show_guard_take_the_send(monkeypatch):
    """Disarm: with the hand-off moved back behind the ladder, the «a ver» sentence is a show again (seen red)."""
    from nucleo.flash import tool_executor_widget_calls as calls
    monkeypatch.setattr(calls, "_leaving_is_a_task", lambda *a, **k: False)
    shown = []
    esc = {"v": None, "surface": {}}
    calls._handle_widget_data_tool(
        {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Quinn", "text": TEXT}},
        _apply_widget_data=lambda *a, **k: None, _brief=None,
        _frontend=SimpleNamespace(payload_ref=lambda *a, **k: ""), _identify=lambda *_a: "", _repeat_repair=None,
        _say=None, _tag_emit=lambda verb, extra: shown.append((verb, extra.get("id"))), acted={}, brain=None,
        clarify={}, deduped={"v": False}, emit=lambda *a, **k: None, escalate_req=esc, text=ORDER)
    assert shown == [("show", "mensajeria")] and esc["v"] is None

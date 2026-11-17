"""Two voice sessions of 2026-11-17, replayed through the send's path: one task, three lines, one send (V2-931).

19:16–19:20 — nothing left. «A ver, …, ¿me vas a mandar un mensaje a Quinn diciéndole que estamos en batería?»: the
show guard read the bare «ver» and swapped the model's `send_to` for a show of the card; one sentence of 28 s reached
the engine as three turns, each opening its own send row and cancelling the last; his yes arrived as two chunks, the
binder read it at 0.04 and the second chunk alone was refused.

23:03–23:10 — it left, and he was left unsure. «Mira, le vas a mandar un mensaje a Quinn y le vas a dar las buenas
noches.»: the box on the card was empty, the question was said as «one of the running processes asks: …», his yes
(«mensaje.» … «Johnny, puedes mandar el mensaje.») resumed the worker (60 s held) and was acknowledged twice, and the
final line — said 2 s after queuing — was «it is queued, not confirmed yet» while the card already showed it sent.

Replayed here against the real doors — the turn's hand-off, the worker's bridge (`worker_act`), the exit door, the row
and its question, the switchboard, the answer door, the receipt's follower — with doubles for the worker (a script
that follows the send's method), the routing model (the decisions it gave on these chunks, measured live), the card's
store and the connector. The people are invented.
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
NIGHT = "Mira, le vas a mandar un mensaje a Quinn y le vas a dar las buenas noches."
NIGHT_TEXT = "Buenas noches"
PIECE, NIGHT_YES = "mensaje.", "Johnny, puedes mandar el mensaje."
UID = "b0-7"
DRAFT = {"widget_id": "mensajeria", "action": "draft", "payload": {"contact": "Quinn Ferrer", "text": NIGHT_TEXT}}
SEND = {"widget_id": "mensajeria", "action": "send_draft", "payload": {"contact": "Quinn Ferrer"}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import dispatch
    from nucleo.circuit import verify
    from nucleo.cli import worker_api, worker_api_answer, worker_api_resume
    from nucleo.pulse import notices
    from nucleo.request import send_receipt
    from nucleo.switchboard import route
    from widgets import contract, server_api
    from widgets.contactos import data as contacts
    worker_api._ACTS.clear()
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    w = SimpleNamespace(sent=[], resumed=[], injects=[], events=[], spoken=[], lines=[], api=worker_api,
                        card={"draft": None, "outbox": []}, kind="yes")

    async def _card(wid, act, payload):                         # the card's store and the connector, doubled
        w.sent.append((wid, act, dict(payload)))
        if act == "draft":
            w.card["draft"] = {"to": payload.get("contact"), "text": payload.get("text")}
            return {"ok": True, "held": True, "to": payload.get("contact")}
        if act in ("send_draft", "send_to"):
            text = (w.card["draft"] or {}).get("text") or payload.get("text")
            w.card["outbox"].append({"ref": f"o{len(w.card['outbox']) + 1}", "state": "queued", "reason": "",
                                     "name": payload.get("contact"), "text": text})
            w.card["draft"] = None
            return {"ok": True, "to": payload.get("contact"), "text": text, "ref": w.card["outbox"][-1]["ref"]}
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _card)
    monkeypatch.setattr(contract, "would_refuse", lambda wid, act, inner: None if (
        act != "send_draft" or w.card["draft"]) else {"error": "no_draft", "message": "There is no draft to send."})
    monkeypatch.setattr(verify, "card_view", lambda wid: dict(w.card))
    monkeypatch.setattr(verify, "check", lambda dw, now=None: any(r["state"] == "sent" for r in w.card["outbox"]))
    monkeypatch.setattr(send_receipt, "end_state", lambda wid, act, inner: {"widget": wid, "collection": "outbox"})
    monkeypatch.setattr(send_receipt, "record_end_state", lambda *a, **k: None)
    monkeypatch.setattr(send_receipt, "POLL_S", 0.01)

    async def _notify(title, text, **kw):
        w.lines.append((kw.get("key", ""), text))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(contacts, "people_named", lambda q, limit=4: [
        {"name": "Quinn Ferrer", "channels": ["whatsapp"]}] if "quinn" in q.lower() else [])
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: w.events.append(
        {"kind": kind, "label": label, "text": text, **(extra or {})}))
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e, src="answer": w.resumed.append(dict(e)) or 1)
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: w.injects.append((which, words)))
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    now = int(time.time())
    ts.task_put({"id": UID, "goal": NIGHT, "title": "Message to Quinn", "state": "running", "playbook": "message",
                 "created_at": now - 5, "started_at": now - 5})
    w.rec = SimpleNamespace(task_id="7", uid=UID, native_sid="sess-1", waiting_on="", ask="", ask_corr="", parked=False,
                            started=time.time(), depth=0, trace_id="", surface="", sheet="", mandate={},
                            playbook_chosen="message", parent_task_id="", kind="generic", goal=NIGHT)
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: w.rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: w.rec)
    monkeypatch.setattr(route, "ask_the_model", lambda text, procs, last="", before=None: (1, "double", w.kind))
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


async def _prepared(world) -> dict:
    """The worker's half of the method: who, the draft where he sees it, the send that asks."""
    who = await _act(world, "find_contact", {"name": "Quinn"})
    assert [p["name"] for p in who["result"]["people"]] == ["Quinn Ferrer"]
    assert (await _act(world, "widget_data", DRAFT)).get("ok") is True
    assert world.card["draft"] == {"to": "Quinn Ferrer", "text": NIGHT_TEXT}, "the text is in the card's box"
    got = await _act(world, "widget_data", SEND)
    assert got.get("status") == "pending" and world.card["outbox"] == [], got
    return got


def _asks(world) -> list:
    return [e for e in world.events if e["kind"] == "ask"]


async def _landed(world, state="sent", reason="") -> None:
    """The connector's own receipt for the queued order — and the follower's next looks at it."""
    world.card["outbox"][-1].update(state=state, reason=reason)
    for _ in range(40):
        await asyncio.sleep(0.01)
        if any(k.endswith((":sent", ":failed")) for k, _t in world.lines):
            return


def test_the_night_send_is_three_lines_and_no_resumed_worker(world):
    """23:03 — the draft in the box, ONE short ask, his yes in pieces decided at once, «sent» only on the receipt."""
    from i18n import langs
    from nucleo.switchboard import board, route
    lang = langs.current_language()

    async def session():
        await _prepared(world)
        (asked,) = _asks(world)
        assert asked["text"] == lang.send_ready_confirm.format(who="Quinn"), asked["text"]
        assert "process" not in asked["text"].lower() and "Ferrer" not in asked["text"]
        assert [(p["key"], p["state"]) for p in board.open_processes()] == [(UID, "waiting")]
        # «mensaje.» — a piece that says nothing yet: nobody is resumed, nothing is said
        world.kind = "fragment"
        assert await route.take(PIECE, emit=world.emit, say=world.spoken.append) is True
        assert world.resumed == [] and world.spoken == [] and world.card["outbox"] == []
        # «Johnny, puedes mandar el mensaje.» — his yes: the act runs NOW, and he hears the one «sending» line
        world.kind = "yes"
        assert await route.take(NIGHT_YES, emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
        assert world.spoken == [lang.send_going]
        assert [r["state"] for r in world.card["outbox"]] == ["queued"] and world.card["outbox"][0]["text"] == NIGHT_TEXT
        assert world.resumed == [], "his yes resumes no session: the engine sends and follows the receipt"
        assert world.lines == [], "queued is not sent: nothing is said before the connector's receipt"
        assert ts.task_get(UID)["state"] != "done"
        await _landed(world)
        assert [t for _k, t in world.lines] == [lang.send_done], world.lines
        assert ts.task_get(UID)["state"] == "done", "the row ends with the verdict the line says"

    asyncio.run(session())
    assert len(_asks(world)) == 1 and [s[1] for s in world.sent] == ["draft", "send_draft"]


def test_a_send_the_connector_refuses_is_said_with_its_reason(world):
    from i18n import langs

    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        assert await route.take("sí, mándalo", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
        await _landed(world, "failed", "the number is not on WhatsApp")
    asyncio.run(session())
    (line,) = [t for _k, t in world.lines]
    assert line == langs.current_language().send_failed.format(why="the number is not on WhatsApp")
    assert ts.task_get(UID)["state"] == "failed"


def test_a_late_receipt_is_said_unconfirmed_once_and_then_sent(world, monkeypatch):
    """No receipt within the bound: ONE line says so; when it lands he is told — never a final line left in doubt."""
    from i18n import langs
    from nucleo.request import send_receipt
    monkeypatch.setattr(send_receipt, "RECEIPT_S", 0.05)
    lang = langs.current_language()

    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        assert await route.take("yes", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.25)
        assert [t for _k, t in world.lines] == [lang.send_unconfirmed]
        await _landed(world)
    asyncio.run(session())
    assert [t for _k, t in world.lines] == [lang.send_unconfirmed, lang.send_done]


def test_his_no_ends_the_send_with_one_line_and_no_worker(world):
    from i18n import langs

    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        world.kind = "no"
        assert await route.take("no, déjalo", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
    asyncio.run(session())
    assert world.spoken == [langs.current_language().send_not_sent]
    assert world.card["outbox"] == [] and world.resumed == [] and world.lines == []
    assert ts.task_get(UID)["state"] == "cancelled"


def test_an_answer_that_is_neither_resumes_the_worker_which_confirms_the_retained_act(world):
    """19:19 — «Vale, mi respuesta es que sí, ¿vale? pero precisamente al mensaje que me acabas de leer.» read as
    «other»: the worker gets his words, reads them as the confirmation and runs THE retained act, once."""
    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        world.kind = "other"
        assert await route.take(YES_1, emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
        assert world.card["outbox"] == [] and len(world.resumed) == 1 and world.resumed[0]["answer"] == YES_1
        assert world.resumed[0]["result"] == {"ok": False, "unclear": True}
        ran = await _act(world, "confirm_send")
        assert ran.get("ok") is True and len(world.card["outbox"]) == 1, ran
        again = await _act(world, "confirm_send")
        assert again.get("ok") is False and len(world.card["outbox"]) == 1, "the same yes never sends twice"
        await _landed(world)
    asyncio.run(session())
    from i18n import langs
    assert [t for _k, t in world.lines] == [langs.current_language().send_done]
    assert len(_asks(world)) == 1


def test_the_buttons_yes_sends_with_no_model_and_no_spoken_ack(world):
    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        world.kind = "other"                                    # the model is not asked: the declared answer decides
        assert await route.take("Yes.", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.05)
    asyncio.run(session())
    assert len(world.card["outbox"]) == 1 and world.resumed == []
    last = [e for e in world.events if e.get("event") == "switchboard"][-1]
    assert (last["by"], last["is"]) == ("declared", "yes")


def test_disarmed_the_final_line_is_said_on_queuing(world, monkeypatch):
    """Disarm: a `receipt` that reads «queued» as sent says «sent» before the connector answered (seen red)."""
    from nucleo.request import send_receipt
    monkeypatch.setattr(send_receipt, "receipt", lambda wid, ref, dw: ("sent", ""))

    async def session():
        from nucleo.switchboard import route
        await _prepared(world)
        assert await route.take("yes", emit=world.emit, say=world.spoken.append) is True
        await asyncio.sleep(0.1)
    asyncio.run(session())
    assert world.card["outbox"][0]["state"] == "queued" and len(world.lines) == 1, "the disarm did not take"


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

"""Several things he asks at once are several tasks (INI-078, Q-7) — the model is told so, and nothing folds them back.

The model reads what each act is from what `declared.json` declares: `start_task` says one call per thing. The
dispatcher's dedup folds a new errand into a live one that looks like it — right for the same order said again, wrong
for two calls of ONE run: «book the hotel in Rome and the flight to Rome» shares the subject and is two tasks. A call
carries its run, and the dedup never takes a sibling of that run as its duplicate (nor a parked one).
"""
from __future__ import annotations

import asyncio

import pytest

import bus
from memory import db as memdb
from nucleo import dispatch

HOTEL = "Reserva un hotel en Roma del 3 al 6 de marzo cerca del Trastevere"
FLIGHT = "Reserva un hotel en Roma del 3 al 6 de marzo cerca del Trastevere y el vuelo de ida"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_the_model_is_told_one_call_per_thing():
    from nucleo.conversation_host import acts
    start = next(t for t in acts.catalog() if t.name == "start_task")
    assert "one call per thing he asks" in start.about


def test_the_call_carries_its_run(monkeypatch):
    from nucleo.conversation_host import acts_tasks, turns
    monkeypatch.setitem(turns._in_course, "run", "run-7")
    assert acts_tasks.errand_context({})["run"] == "run-7"


def _second_escalation(monkeypatch, run_of_live: str, run_of_new: str) -> tuple[list, list]:
    from nucleo.acts import errand as escalate
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "_SESSIONS", {}, raising=False)
    from tests.agent_headless.unit.test_dispatch import _FakeBackend
    monkeypatch.setattr(dispatch, "get_backend", lambda spec: _FakeBackend())
    injected: list = []

    async def _inject(which, msg):
        injected.append(which)
        return [which]
    monkeypatch.setattr(dispatch, "inject", _inject)

    async def run():
        bus.reset()
        escalate.reset()
        dispatch._SESSIONS["live"] = SessionRecord(task_id="live", kind="web", status="running", goal=HOTEL,
                                                   run=run_of_live)
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        escalate.escalate_to_slowbrain(FLIGHT, context={"kind": "web", "run": run_of_new})
        await asyncio.sleep(0.2)
        born = [k for k in dispatch._SESSIONS if k != "live"]
        stop.set()
        await asyncio.sleep(0.05)
        task.cancel()
        return born
    return asyncio.run(run()), injected


def test_two_calls_of_one_run_on_one_subject_are_two_tasks(fresh_db, monkeypatch):
    born, injected = _second_escalation(monkeypatch, "run-1", "run-1")
    assert injected == [] and len(born) == 1, "a sibling of the same run is its own task, never folded"


def test_the_same_order_said_again_in_another_run_still_folds(fresh_db, monkeypatch):
    born, injected = _second_escalation(monkeypatch, "run-1", "run-2")
    assert injected == ["live"] and born == []


def test_a_parked_sibling_of_the_same_run_is_not_its_duplicate(monkeypatch):
    from nucleo.dispatch import confirm
    monkeypatch.setattr(confirm, "_PENDING_CONFIRM", {"9": {"request": HOTEL, "ts": 9e12, "context": {"run": "run-1"}}})
    monkeypatch.setattr(confirm, "_sweep_confirm", lambda: None)
    assert confirm.parked_errands("run-1") == [] and confirm.parked_errands("run-2") == [("9", HOTEL)]


TWELVE = "\n".join(f"{i}. Busca y compárame {i} opciones de algo distinto, con todos los detalles que encuentres: "
                   + "precio, plazos, opiniones y dónde comprarlo. " * 6 for i in range(1, 13)).strip()


def test_a_long_message_of_twelve_things_enters_whole_by_both_doors(monkeypatch):
    """Twelve things in one typed message — past the 4000 characters the doors used to keep — reach the
    conversation WHOLE: a typed line and a device's ear alike. A limit that loses his words is an error (operator)."""
    from nucleo.conversation_host import controls, ear_in, entry
    assert len(TWELVE) > 4000, "the case must be past the old cut, or this test proves nothing"
    heard = []
    monkeypatch.setattr(entry, "_hand", lambda fn: fn(type("Conv", (), {"hear": lambda self, sig: heard.append(sig)})()))
    monkeypatch.setattr(ear_in, "heard_lately", lambda s: [])
    entry.typed(TWELVE, "keyboard:1", checked=True)
    controls.local_phrase(TWELVE, "browser:1")
    assert [sig.text for sig in heard] == [TWELVE, TWELVE]


def test_the_screens_door_and_the_chat_box_keep_it_whole(monkeypatch):
    import asyncio
    from pathlib import Path

    from server import screens_api
    from voice import screens
    got = []

    async def deliver_typed(text, dev, cid=""):
        got.append(text)
        return True
    monkeypatch.setattr(screens, "deliver_typed", deliver_typed)
    monkeypatch.setattr("nucleo.runstate.stopped", lambda: False)
    asyncio.run(screens_api.chat(text=TWELVE, dev="phone-1", cid=""))
    assert got == [TWELVE]
    chat = (Path(__file__).resolve().parents[4] / "frontend/app/components/ChatWall.js").read_text(encoding="utf-8")
    send = chat[chat.index("export function submitChat"):]
    assert ".slice(0, MAX_TEXT)" not in send[:send.index("\n}")], "the chat box sends what he typed, whole"


def test_an_event_enters_whole():
    """An inbound message or mail is data the code and his rules decide on: its text enters the conversation whole."""
    from nucleo.conversation_host import events_in
    env = events_in.envelope({"origin": "email", "text": TWELVE, "fields": {"platform": "email"}}, {}, "ev-1", 1000)
    assert env.body.text == TWELVE

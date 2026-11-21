"""V2-799 — a turn about PENDING work resolves to the durable pending rows, and each one resumes FROM ITS ROW.

Live (2026-10-26): an email held for his «send it» and a table hunt waiting for his pick. «termina esas tareas»: the
model wrote two complete commissions; the fragment guard annulled both, a backstop glued an old utterance to the new
one («Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — termina esas tareas»), date/time/party/area were
lost, and the worker refused. The refusal then became the browser card's title.

Here: Spanish and English turns; an email + an errand pending together; one pending; none pending (and then the
verdict is never paid for); a live errand is not started twice; the card title is the errand's name.
"""
from __future__ import annotations

import asyncio
import pathlib
import time

import pytest

from nucleo import pending_work
from nucleo.flash import resume_turn
from tests.outbound_lane import his_hand  # noqa: F401,E402 — these tests run the card's own acts, as his hand

ROOT = pathlib.Path(__file__).resolve().parents[4]
GOAL = "Reserva mesa para 2 el lunes a las 14:00 en un restaurante del centro de Soria"


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    resume_turn.reset()
    pending_work.forget_cache()
    from nucleo.circuit import ledger as tasks
    ts = tasks.store()
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    yield
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    resume_turn.reset()
    pending_work.forget_cache()


def _errand(uid="b00t01-1", state="done", goal=GOAL, outcome="La que mejor encaja: Garoa — ¿te la reservo?"):
    from nucleo.circuit import ledger as tasks
    now = int(time.time())
    tasks.store().task_put({"id": uid, "title": "Reservar mesa en Soria", "goal": goal, "kind": "web", "mode": "now",
                            "state": state, "visible": True, "origin": "voz", "created_at": now - 600,
                            "started_at": now - 600, "finished_at": now - 60 if state == "done" else None,
                            "outcome": outcome, "sheet": "results--3"})


def _held_email():
    from widgets.mensajeria import data
    data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access", "text": "Hola"})


def _verdict(monkeypatch, wanted_sources, calls):
    from nucleo import jev

    def pick(rows, criteria, **_k):
        calls.append(criteria)
        return [{"candidate": r, "fit": "strong", "confidence": 0.95} for r in rows if r["source"] in wanted_sources]
    monkeypatch.setattr(jev, "select_many", pick)


def _escalations(monkeypatch):
    from nucleo.acts import errand as escalate
    got = []
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: got.append((req, context)) or 1)
    return got


def _take(text, ops):
    req = {"v": "Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — " + text, "more": []}
    took = asyncio.run(resume_turn.take(req, operator_text=text, last_reply="Hecho.",
                                        apply_widget_data=lambda w, a, p: ops.append((w, a, p))))
    return took, req


def test_nothing_pending_pays_no_verdict_and_keeps_todays_path(monkeypatch):
    calls, ops = [], []
    _verdict(monkeypatch, {"task", "widget"}, calls)
    took, req = _take("termina esas tareas", ops)
    assert not took and calls == [] and req["v"] is not None


def _fragment_turn(monkeypatch, text, *, ask_rows: bool = True):
    """A short turn about pending work, with the model's commission glued to an old utterance, passed through the two
    steps in the order the turn runs them: the rows are asked, then the fragment guard reads what is left."""
    from nucleo.flash import escalation_guard
    _errand()
    calls = []
    _verdict(monkeypatch, {"task"}, calls)
    esc = _escalations(monkeypatch)
    if not ask_rows:                                            # the disarm: the rows are never asked
        async def _skip(*a, **k):
            return None
        monkeypatch.setattr(resume_turn, "before_fragment_guard", _skip)
    req, acted = {"v": "Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — " + text, "more": []}, {}
    asyncio.run(resume_turn.before_fragment_guard(req, operator_text=text, brief=None, last_reply="Hecho.",
                                                  apply_widget_data=None, emit=None, acted=acted))
    annulled = escalation_guard.drop_if_fragment(req, operator_text=text, brief=None, last_reply="Hecho.")
    return req, esc, annulled


def test_the_disarm_a_guard_that_runs_before_the_rows_annuls_the_resumption(monkeypatch):
    """Disarm: with the rows never asked, the same turn is annulled as a fragment and nothing resumes."""
    req, esc, annulled = _fragment_turn(monkeypatch, "acaba eso", ask_rows=False)
    assert annulled and esc == [] and "resumed" not in req and req["v"] is None


def test_both_doors_ask_the_rows_before_annulling_or_gluing():
    """Kept as a SOURCE check: the call ORDER inside the two turn bodies (`complete_the_acts`, `run_the_light_lanes`,
    each taking ~40 closure arguments) cannot be observed without driving the whole voice turn. What that order
    buys is the behaviour test above."""
    words = (ROOT / "nucleo/flash/post_stream_acts.py").read_text(encoding="utf-8")
    assert words.index("_resume_turn.before_fragment_guard(") < words.index("_pst._eguard.drop_if_fragment(")
    lanes = (ROOT / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    i = lanes.index("_no_tool = await _pst._resume_turn.before_backstops(")
    assert i < lanes.index('escalate_req["v"] = _op_text')


# ── the card's title is the errand's NAME, never a summariser's or a worker's sentence ──────────────────

def test_the_card_title_is_the_errand_name_and_a_summary_never_overwrites_it():
    from widgets.navegador import data as navdata, tasks as navtasks
    tid = navtasks.create("Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — termina esas tareas",
                          "Reservar restaurante")
    navtasks.set_goal_summary(tid, "No se puede: la petición no contiene objetivo, criterios, tipo")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Reservar restaurante"
    navtasks.set_title(tid, "Mesa para 2 en Soria")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Mesa para 2 en Soria"


REQ = "Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — finish those two things"


def _web_card(monkeypatch, title: str):
    """The browser card `_prepare_web` opens for an errand, and the same card after the namer named the errand."""
    from types import SimpleNamespace

    from nucleo import dispatch
    from nucleo.agentes import web as agweb
    from nucleo.request import title as errand_title
    from widgets.navegador import data as navdata, tasks as navtasks

    async def _refusal(goal):
        return "No se puede: la petición no contiene objetivo, criterios, tipo"
    monkeypatch.setattr(agweb, "_synthesize_goal", _refusal)
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    monkeypatch.setattr(navtasks, "_tasks", {})          # the registry is process state: no tab from another test
    rec = SimpleNamespace(title=title, goal=REQ, trace_id="", task_id="b00t01-9", surface="", status="running",
                          nav_task="")
    tid = asyncio.run(dispatch._prepare_web(rec, REQ))
    born = navdata._task_view(navtasks.get(tid))["title"]
    monkeypatch.setattr(errand_title, "enabled", lambda: True)

    async def _named(goal, **_k):
        return "Table for two in Soria"
    monkeypatch.setattr(errand_title, "compose", _named)

    async def _name():
        dispatch._name_errand(rec)
        await asyncio.gather(*list(dispatch._TITLE_BG_TASKS))
    asyncio.run(_name())
    return born, navdata._task_view(navtasks.get(tid))["title"], rec


def test_a_browser_card_is_born_with_the_errands_name_and_renamed_with_it(monkeypatch):
    born, renamed, rec = _web_card(monkeypatch, "Mesa en Soria")
    assert born == "Mesa en Soria", "born with the errand's name, never the utterance or the summariser's refusal"
    assert renamed == "Table for two in Soria" == rec.title, "the namer's name reaches the app the errand opened"


def test_an_unnamed_errand_card_is_born_with_the_provisional_name_never_the_utterance(monkeypatch):
    from nucleo.request import title as errand_title
    born, _renamed, _rec = _web_card(monkeypatch, "")
    assert born == errand_title.provisional(REQ) and "No se puede" not in born


# ── the MODEL resumes, from the state it is shown; the verdict only completes it ─────────────────────────

def _live_state_pending(with_rows: bool) -> list[str]:
    """The PENDIENTE block as the turn prompt's live state carries it (`nucleo.turn.prompt.live_state`)."""
    from nucleo.turn.prompt import live_state as prompt
    if with_rows:
        _errand(uid="b00t01-4", goal="Find a dentist open on Saturday", outcome="Two fit — want me to book one?")
        _held_email()
    pending_work.forget_cache()
    state = prompt.live_state().splitlines()
    i = next((n for n, line in enumerate(state) if line.startswith("PENDIENTE")), None)
    return [] if i is None else state[i:i + 1 + len(pending_work.rows())]


def test_the_disarm_a_live_state_without_the_pending_block(monkeypatch):
    """Disarm: when the live block yields nothing, the prompt loses the rows the model resumes by id."""
    from nucleo.turn.prompt import live_history
    monkeypatch.setattr(live_history, "pending_work_lines", lambda: [])
    assert _live_state_pending(True) == []


def test_the_resume_tool_is_offered_only_when_something_is_pending():
    from nucleo.flash import router
    names = lambda ctx: [t["function"]["name"] for t in router.tools(ctx)]   # noqa: E731
    assert "resume_task" in names(router.tool_context(has_pending=True))
    assert "resume_task" not in names(router.tool_context(has_pending=False))


# ── the harness: «confirmed» and «done» are checked separately ──────────────────────────────────────────

def test_a_confirmed_send_owes_its_end_state_and_a_send_that_did_not_happen_is_unmet():
    """A «yes» that leads to nothing must be impossible: the confirmed path (`dispatch_and_report(receipt=True)`)
    opens the action's declared end state, and `send_draft` now declares one — a sent row for that recipient."""
    from nucleo.circuit import spec
    from widgets.mensajeria import data
    _held_email()
    e = spec.open_for_action("mensajeria", "send_draft", {"contact": "hospitality@example.com"}, text="sí")
    assert e is not None, "the end state must render for a held send"
    assert spec.attest(e) is False, "nothing sent yet: unmet, never a silent «done»"
    res = data.apply_action("send_draft", {"contact": "hospitality@example.com"})
    assert spec.attest(e) is False, "V2-847: queued is not sent — the end state is the connector's echo"
    # Changed on purpose 2026-11-08: our order's outbox row, settled by the connector's echo, is the end state.
    db = data.load_db()
    db.setdefault("threads", {})["email|hospitality@example.com"] = {"name": "hospitality@example.com", "msgs": [
        {"id": "phone-1", "dir": "out", "who": "Tú", "body": "ok", "ts": time.time()}]}
    data.store.save(data.WIDGET_ID, db)
    assert spec.attest(e) is False, "a message in the thread that is not our order's echo is not its landing"
    from widgets.mensajeria import owner
    owner._settle(res["ref"], True)                  # the connector's echo bound to our ref (`_apply_outbound`)
    assert spec.attest(e) is True


def test_listing_pending_rows_does_not_import_a_widget_that_declares_none(monkeypatch):
    """G1 (2026-11-19): `_widget_rows` imported every widget's data module on the event loop to learn whether it
    declares `pending_rows` — the music card's alone held a cloud host's loop 1.6 s. A module whose source does not
    name the hook is never imported; one that does (mail) still offers its rows."""
    import importlib
    import sys

    from widgets import runtime
    monkeypatch.setattr(runtime, "catalog", lambda: [{"id": "musica"}, {"id": "mensajeria"}])
    monkeypatch.delitem(sys.modules, "widgets.musica.data", raising=False)
    imported, real = [], importlib.import_module
    monkeypatch.setattr(importlib, "import_module", lambda name, *a: imported.append(name) or real(name, *a))
    pending_work._widget_rows()
    assert "widgets.musica.data" not in imported, "a widget that declares no pending rows was imported to list them"
    assert "widgets.mensajeria.data" in imported, "a widget that declares the hook is still read"

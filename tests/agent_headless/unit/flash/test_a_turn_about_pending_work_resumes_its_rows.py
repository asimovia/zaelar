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

ROOT = pathlib.Path(__file__).resolve().parents[4]
GOAL = "Reserva mesa para 2 el lunes a las 14:00 en un restaurante del centro de Soria"


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    resume_turn.reset()
    from nucleo import tasks
    ts = tasks.store()
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    yield
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    resume_turn.reset()


def _errand(uid="b00t01-1", state="done", goal=GOAL, outcome="La que mejor encaja: Garoa — ¿te la reservo?"):
    from nucleo import tasks
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
    from nucleo.flash import escalate
    got = []
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: got.append((req, context)) or 1)
    return got


def _take(text, ops):
    req = {"v": "Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — " + text, "more": []}
    took = asyncio.run(resume_turn.take(req, operator_text=text, last_reply="Hecho.",
                                        apply_widget_data=lambda w, a, p: ops.append((w, a, p))))
    return took, req


@pytest.mark.parametrize("text", ["termina esas tareas", "finish those two things"])
def test_an_email_and_an_errand_pending_together_both_resume_from_their_rows(monkeypatch, text):
    _errand()
    _held_email()
    calls, ops = [], []
    _verdict(monkeypatch, {"task", "widget"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take(text, ops)
    assert took and req["v"] is None and req["more"] == [] and len(req["resumed"]) == 2
    # the email: through its OWN declared action (its own confirm gate), named by its recipient
    assert ops == [("mensajeria", "send_draft", {"contact": "hospitality@example.com"})]
    # the errand: its own brief verbatim, its row and its sheet — no glued utterance, no blind restart
    (brief, ctx), = esc
    assert brief.startswith(GOAL) and "Garoa" in brief and text in brief
    assert "Serías capaz" not in brief
    assert ctx["task_uid"] == "b00t01-1" and ctx["sheet"] == "results--3" and ctx["src"] == "resume"


def test_one_pending_row_is_one_resumption(monkeypatch):
    _errand()
    calls, ops = [], []
    _verdict(monkeypatch, {"task"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take("sigue con lo de antes", ops)
    assert took and len(esc) == 1 and ops == []


def test_nothing_pending_pays_no_verdict_and_keeps_todays_path(monkeypatch):
    calls, ops = [], []
    _verdict(monkeypatch, {"task", "widget"}, calls)
    took, req = _take("termina esas tareas", ops)
    assert not took and calls == [] and req["v"] is not None


def test_a_turn_that_means_no_pending_row_keeps_todays_path(monkeypatch):
    _errand()
    calls, ops = [], []
    _verdict(monkeypatch, set(), calls)
    took, req = _take("ponme música", ops)
    assert not took and len(calls) == 1 and req["v"] is not None


def test_a_live_errand_is_not_started_twice(monkeypatch):
    _errand(uid="b00t01-2", state="waiting")
    calls, ops = [], []
    _verdict(monkeypatch, {"task"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take("termina esa tarea", ops)
    assert took and esc == [] and req["resumed"] == ["b00t01-2"]


def test_both_doors_ask_the_rows_before_annulling_or_gluing():
    words = (ROOT / "nucleo/flash/post_stream_words.py").read_text(encoding="utf-8")
    assert words.index("_resume.take(escalate_req") < words.index("_pst._eguard.drop_if_fragment(")
    lanes = (ROOT / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    i = lanes.index("_resume.take(escalate_req")
    assert i < lanes.index('escalate_req["v"] = _win_goal or _op_text')
    assert lanes.count('not escalate_req.get("resumed")') >= 2, "both backstops step aside once the rows resumed"


# ── the card's title is the errand's NAME, never a summariser's or a worker's sentence ──────────────────

def test_the_card_title_is_the_errand_name_and_a_summary_never_overwrites_it():
    from widgets.navegador import data as navdata, tasks as navtasks
    tid = navtasks.create("Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — termina esas tareas",
                          "Reservar restaurante")
    navtasks.set_goal_summary(tid, "No se puede: la petición no contiene objetivo, criterios, tipo")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Reservar restaurante"
    navtasks.set_title(tid, "Mesa para 2 en Soria")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Mesa para 2 en Soria"


def test_a_browser_card_is_born_with_the_errands_name_and_renamed_with_it():
    src = (ROOT / "nucleo/dispatch_prepare.py").read_text(encoding="utf-8")
    assert "navtasks.create(req, _errand_name(rec, req)" in src
    assert "_navtasks.set_title(rec.nav_task, t)" in src

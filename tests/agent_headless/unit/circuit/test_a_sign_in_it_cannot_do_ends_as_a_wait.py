"""A sign-in the engine cannot do ends the errand as a WAIT on him, never as a result (V2-868 D3).

Measured on the operator's console: an errand driving a seller's page landed on the sign-in; its worker kept going and
wrote its own status («login pending», a daily hour) and a recalled price as a finding. When the card it drives waits
for his sign-in — a window open for him, or no window that can reach him — the errand asks him ONE question through
THE asker, its worker stops (parked: its ending writes nothing), and his confirmed sign-in resumes the SAME row. The
phone's line says the window opens on a computer. And an errand the composer said is not a research owes no results
sheet: its prompt never names one.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.request import sign_in_wait
from nucleo.workers.session import SessionRecord


class _Backend:
    def __init__(self):
        self.stopped = 0

    async def stop(self, grace: float = 3.0):
        self.stopped += 1


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    sign_in_wait._reset_for_tests()
    from nucleo import dispatch
    from widgets.navegador import tasks
    nav = tasks.create("track my parcel with the seller's bot")
    rec = SessionRecord(task_id="21", goal="track my parcel", kind="web", uid="cafe03-21", status="running")
    rec.nav_task = nav
    rec.session = type("S", (), {"_b": _Backend()})()
    ts.task_put({"id": rec.uid, "goal": rec.goal, "state": "running", "created_at": 1, "started_at": 1})
    monkeypatch.setitem(dispatch._SESSIONS, rec.task_id, rec)
    yield rec, nav
    sign_in_wait._reset_for_tests()
    memdb.reset_db()


def test_a_login_wait_parks_the_errand_with_one_question_and_stops_its_worker(world):
    rec, nav = world
    from widgets.navegador import tasks
    from nucleo.workers import session_finish

    async def _go():
        tasks.set_login_wait(nav, True)
        await asyncio.sleep(0)
    asyncio.run(_go())
    assert rec.parked and rec.waiting_on == "user" and session_finish.parked(rec), "its ending writes nothing"
    assert rec.session._b.stopped == 1, "the worker does not keep running past the sign-in"
    row = ts.task_get(rec.uid)
    assert row["state"] == "waiting" and row["waiting_for"] == "user_answer" and row["ask"] == rec.ask
    from nucleo.circuit import asker
    art = asker.artefact(rec.uid)
    assert art["sign_in"] is True and art["nav_task"] == nav and not (art.get("retained") or {}).get("action"), \
        "nothing runs on his yes: it is a question, not a retained act"


def test_one_question_only_even_when_the_card_says_it_twice(world):
    rec, nav = world
    first = sign_in_wait.park(nav)
    assert first and sign_in_wait.park(nav, blocked="no_window") == ""


def test_a_blocked_card_from_the_phone_says_the_window_opens_on_a_computer(world, monkeypatch):
    rec, nav = world
    from voice import screens
    monkeypatch.setattr(screens, "task_origin", lambda tid: "mobile:abc" if tid == rec.task_id else "")
    from i18n import runtime as _rt
    phone = _rt.text("errand.sign_in.phone", default="")
    assert phone and sign_in_wait.question(rec, blocked="no_window") == phone
    monkeypatch.setattr(screens, "task_origin", lambda tid: "desktop:abc")
    assert sign_in_wait.question(rec, blocked="no_window") == _rt.text("errand.sign_in.no_window", default="")
    assert sign_in_wait.question(rec) == _rt.text("errand.sign_in.window", default="")


def test_the_lines_exist_in_both_languages_with_the_same_keys():
    import json
    root = Path(__file__).resolve().parents[4] / "i18n" / "genesis"
    keys = {lang: {k for k in json.loads((root / lang / "ui.json").read_text()) if k.startswith("errand.sign_in.")}
            for lang in ("es", "en")}
    assert keys["es"] == keys["en"] == {"errand.sign_in.window", "errand.sign_in.no_window", "errand.sign_in.phone",
                                        "errand.sign_in.done"}


def test_his_confirmed_sign_in_resumes_the_same_row_and_an_abandoned_window_does_not(world, monkeypatch):
    rec, nav = world
    ask_id = sign_in_wait.park(nav)
    answered = []
    monkeypatch.setattr(sign_in_wait, "_answer_soon", lambda aid, text: answered.append(aid))
    assert sign_in_wait.established("shop.example.test") == 0, "no wait ended: nothing to resume"
    sign_in_wait.ended(nav)                                     # the card's wait ended (sign-in or abandoned)…
    assert answered == []
    assert sign_in_wait.established("shop.example.test") == 1   # …and the owner CONFIRMED a sign-in
    assert answered == [ask_id], "the errand's own question is answered: the same row resumes by id"


def test_an_errand_the_composer_said_is_not_research_owes_no_results_sheet():
    from nucleo.workers import brief as research
    from nucleo.workers.prompts import playbook, web
    assert playbook.results_contract(None) is True, "a brief still on its way keeps the contract"
    assert playbook.results_contract(research.not_research()) is False
    assert playbook.results_contract({"goal": "x", "deliverable": {"widget": "results"}}) is True
    with_sheet = web._web_prompt("track my parcel", "", None)
    without = web._web_prompt("track my parcel", "", research.not_research())
    assert "cli.widget data results present" in with_sheet and "cli.widget data results present" not in without


def test_disarm_the_wait_not_settled_and_the_worker_keeps_running(world):
    rec, nav = world
    src = Path(__file__).resolve().parents[4] / "widgets" / "navegador" / "tasks" / "fields.py"
    orig = src.read_text(encoding="utf-8")
    import importlib
    from widgets.navegador.tasks import fields
    try:
        src.write_text(orig.replace("    _errand_waits(task_id, on, blocked)\n", ""), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(fields)
        fields.set_login_wait(nav, True)
        assert not rec.parked and rec.session._b.stopped == 0, "disarmed, the worker keeps running past the sign-in"
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(fields)

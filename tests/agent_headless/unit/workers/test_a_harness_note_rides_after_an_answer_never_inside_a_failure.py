"""V2-886 fila 9 — a note to the worker travels AFTER an answer that worked, never inside a failed one, and is signed by
its author. Measured 2026-11-11: the pulse's «report your status» demand rode, signed «NEW INSTRUCTIONS FROM THE
OPERATOR», in front of a refused `read_widget`; the worker read it as the answer, and the step's evidence recorded the
harness's voice as the tool's. Disarm: serve the piggyback on a failure again → red."""
import asyncio
from types import SimpleNamespace

import pytest

from nucleo.cli import bridge, widget, worker_api
from nucleo.workers.session import Inject


@pytest.fixture
def worker(monkeypatch):
    rec = SimpleNamespace(task_id="9", uid="r9", injects=[Inject(text="report now", ts=0.0, source="system")])
    monkeypatch.setattr(worker_api, "_verify", lambda tid, tok: rec)
    from nucleo import dispatch
    from nucleo.dispatch import control
    monkeypatch.setattr(dispatch, "_SESSIONS", {"9": rec}, raising=False)
    monkeypatch.setattr(dispatch, "take_pending_injects", control.take_pending_injects)
    from nucleo.workers import task_files
    monkeypatch.setattr(task_files, "record", lambda *a, **k: None)
    monkeypatch.setattr(task_files, "said", lambda *a, **k: None)
    return rec


def _act(monkeypatch, result):
    async def one(rec, action, payload):
        return dict(result)
    monkeypatch.setattr(worker_api, "_one_act", one)
    import json
    resp = asyncio.run(worker_api.worker_act(task_id="9", token="t", action="read_widget", payload={}))
    return json.loads(resp.body)


def test_a_failure_carries_no_note_and_the_note_waits(worker, monkeypatch):
    assert _act(monkeypatch, {"ok": False, "error": "no such card"})["injections"] == []
    assert worker.injects[0].state == "pending", "a note was spent on a failed answer"
    got = _act(monkeypatch, {"ok": True, "result": {"rows": []}})["injections"]
    assert got == [{"text": "report now", "source": "system"}] and worker.injects[0].state == "delivered"


@pytest.mark.parametrize("cli", [bridge, widget])
def test_the_cli_prints_the_note_after_the_result_signed_by_its_author(cli, capsys):
    cli._emit_injections({"injections": [{"text": "report now", "source": "system"},
                                         {"text": "only 4 stars", "source": "operator"}, "legacy text"]})
    out = capsys.readouterr().out.splitlines()
    assert out == ["⟦AVISO DEL SISTEMA⟧ report now", "⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧ only 4 stars",
                   "⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧ legacy text"]


def test_widget_report_prints_the_result_first(capsys):
    widget._report({"ok": False, "error": "no such card", "injections": [{"text": "report now", "source": "system"}]})
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("ERROR:") and out[-1] == "⟦AVISO DEL SISTEMA⟧ report now"

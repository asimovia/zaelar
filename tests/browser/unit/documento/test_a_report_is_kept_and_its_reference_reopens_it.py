"""V2-862 — a report errand's document is KEPT when it ends (finished or half done) and its chat reference reopens IT.

The `documento` card holds ONE document and the next report overwrites it. So a reference on his chat wall that only
said «open the document card» would open the newest report, not the one it names. At its end the errand keeps what it
wrote twice: as a file on his library's documents shelf (where Archivos shows his files) and as the task's `document`
artifact, which the one reopen door (`nucleo/turn/task_recall.reopen`, also `POST /api/tasks/reopen`) rebuilds the
sheet from when the sheet now shows something else.
"""
from __future__ import annotations

import importlib

import pytest

CASES = [
    ("en", "Kitchen hood bulb", "# Kitchen hood bulb\n\nYour bulb is a G9 capsule, 230 V.\n\n## Where to buy\n(loading…)"),
    ("es", "Bombilla de la campana", "# Bombilla de la campana\n\nEs una cápsula G9 de 230 V.\n\n## Dónde comprar\n(cargando…)"),
]


@pytest.fixture()
def doc(tmp_path, monkeypatch):
    """A private workspace: the sheet's store AND the library live under tmp, never his."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.documento import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


@pytest.mark.parametrize("lang,title,body", CASES)
def test_a_half_written_report_is_kept_as_a_file_and_as_the_tasks_copy(doc, tmp_path, lang, title, body):
    doc.begin_task(title, task_id="17")
    assert doc.apply_action("show", {"title": title, "body": body}).get("ok") is not False
    kept = doc.keep_task("17")
    assert kept["body"] == body and kept["title"] == title, f"[{lang}] what it wrote so far is the copy"
    assert kept["file"] == f"documents/{title}.md", f"[{lang}] {kept}"
    assert (tmp_path / "library" / kept["file"]).read_text() == body, f"[{lang}] the text is on his documents shelf"
    assert doc.keep_task("17")["file"] == kept["file"], f"[{lang}] keeping again updates the same file, no «(1)»"
    assert doc.keep_task("99") == {}, "another errand's id keeps nothing of this sheet"


def test_an_empty_sheet_keeps_nothing(doc):
    doc.begin_task("Nothing yet", task_id="5")
    assert doc.keep_task("5") == {}


@pytest.mark.parametrize("lang,title,body", CASES)
def test_the_reference_reopens_ITS_report_after_another_overwrote_the_sheet(doc, monkeypatch, lang, title, body):
    doc.begin_task(title, task_id="17")
    doc.apply_action("show", {"title": title, "body": body})
    kept = doc.keep_task("17")
    doc.finish_task("17", phases=[])
    doc.begin_task("Another report", task_id="18")                 # the next report takes the one sheet
    doc.apply_action("show", {"title": "Another report", "body": "Something else entirely."})

    from nucleo.circuit import ledger
    from nucleo.turn import task_recall
    from widgets.results import rehydrate
    store = {("t-17", "document"): kept}
    monkeypatch.setattr(ledger, "artifact", lambda tid, slot: store.get((tid, slot)))
    monkeypatch.setattr(rehydrate, "sheet_from_task", lambda tid: {"ok": False, "error": "no results"})
    out = task_recall.reopen({"id": "t-17", "title": title})
    assert out["ok"] and out["instance"] == "documento" and out["rebuilt"], f"[{lang}] {out}"
    assert doc.view_data()["body"] == body, f"[{lang}] the sheet shows the report the reference names"


def test_a_card_the_task_kept_is_what_a_surface_without_a_copy_reopens(doc, monkeypatch):
    from nucleo.circuit import ledger
    from nucleo.turn import task_recall
    from widgets.results import rehydrate
    monkeypatch.setattr(ledger, "artifact", lambda tid, slot: {"instance": "plant_tracker"} if slot == "card" else None)
    monkeypatch.setattr(rehydrate, "sheet_from_task", lambda tid: {"ok": False})
    assert task_recall.reopen({"id": "t-3"})["instance"] == "plant_tracker"
    monkeypatch.setattr(ledger, "artifact", lambda tid, slot: None)
    assert not task_recall.reopen({"id": "t-4"}).get("ok"), "nothing kept → no blank card"


def test_the_http_reopen_is_the_same_door_the_voice_uses():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "server/tasks_api.py").read_text()
    body = src.split("async def tasks_reopen", 1)[1].split("@router", 1)[0]
    assert "task_recall" in body and "_recall.reopen" in body

"""A legacy canvas answer that differs from the screen's document is an EVENT (V2-907 T10, node 4.545).

Phase A runs the screen document in shadow beside the legacy canvas state (`memory.state()`: `open_widgets`,
`maximized_widget`, `minimized_widgets`, `front_reported`). `widgets/screen_doc.drift` names, in the legacy store's
own terms, each fact where the two disagree (`open`, a deck's `front`, a desk's `max`, `min`); `server.canvas_api`
measures it after every counted legacy report (once the host's own document has had time to land) and at the start of
every turn, and emits `screen/drift {dev, at, what, legacy, doc}` — family `widget`. Nothing reads it to decide.

Disarm: the comparison compares the document with itself → no drift is ever seen → red.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
DESK, PHONE = "desktop:d-ava", "mobile:m-ava"
_GUARD = "        if old != new:\n"


@pytest.fixture
def screen(monkeypatch):
    from memory import api as memory
    from server import canvas_api
    from voice import screens
    from widgets import screen_doc
    screen_doc._reset_for_tests()
    monkeypatch.setattr(screens, "is_open", lambda dev: screens.clean(dev) in (DESK, PHONE))
    legacy: dict = {}
    monkeypatch.setattr(memory, "state", lambda: dict(legacy))
    events: list = []
    monkeypatch.setattr(canvas_api, "emit", lambda kind, label, **kw: events.append((kind, label, kw)))
    yield screen_doc, legacy, events, canvas_api
    screen_doc._reset_for_tests()


def _write(sd, dev, layout, *rows, n=1):
    doc = {"layout": layout, "open": [{"id": i, "layer": k, "vis": v, **({"max": True} if m else {})}
                                      for k, (i, v, m) in enumerate(rows)]}
    stored, why = sd.write(dev, "k1", n, doc)
    assert stored, why


def test_a_legacy_state_that_agrees_is_no_drift(screen):
    sd, legacy, _, _ = screen
    _write(sd, DESK, "windows", ("youtube", "front", True), ("results::c1", "visible", False), ("agenda", "min", False))
    legacy.update(open_widgets=["youtube", "results", "agenda"], maximized_widget="youtube",
                  minimized_widgets=["agenda"], front_reported=False)
    assert sd.drift(DESK, legacy) == []
    _write(sd, PHONE, "deck", ("musica", "front", False), ("agenda", "behind", False))
    assert sd.drift(PHONE, {"open_widgets": ["musica", "agenda"], "maximized_widget": "musica",
                            "minimized_widgets": ["agenda"], "front_reported": True}) == []


def test_each_disagreement_is_named_in_the_legacy_terms(screen):
    sd, _, _, _ = screen
    _write(sd, DESK, "windows", ("youtube", "front", True), ("agenda", "min", False))
    rows = sd.drift(DESK, {"open_widgets": ["youtube", "agenda", "musica"], "maximized_widget": "",
                           "minimized_widgets": [], "front_reported": False})
    assert rows == [{"what": "open", "legacy": ["agenda", "musica", "youtube"], "doc": ["agenda", "youtube"]},
                    {"what": "max", "legacy": "", "doc": "youtube"},
                    {"what": "min", "legacy": [], "doc": ["agenda"]}]
    _write(sd, PHONE, "deck", ("agenda", "behind", False))                 # the home in view
    rows = sd.drift(PHONE, {"open_widgets": ["agenda"], "maximized_widget": "agenda",
                            "minimized_widgets": [], "front_reported": True})
    assert [r["what"] for r in rows] == ["front", "min"] and rows[0] == {"what": "front", "legacy": "agenda", "doc": ""}


def test_an_unknown_screen_is_not_a_drift(screen):
    sd, _, _, _ = screen
    assert sd.drift(DESK, {"open_widgets": ["agenda"]}) == []        # never reported: nothing to compare


def test_a_counted_legacy_report_measures_the_drift_after_its_grace(screen, monkeypatch):
    sd, legacy, events, api = screen
    from voice import screens
    monkeypatch.setattr(api, "DRIFT_GRACE_S", 0.01)
    monkeypatch.setattr(screens, "current", lambda: DESK)
    legacy.update(open_widgets=["agenda", "musica"], maximized_widget="", minimized_widgets=[], front_reported=False)
    _write(sd, DESK, "windows", ("agenda", "front", False))

    async def _go():
        await api.canvas_state({"open": [], "dev": DESK, "by": {}})
        await asyncio.sleep(0.1)
    asyncio.run(_go())
    drifts = [kw["extra"] for k, lab, kw in events if (k, lab) == ("screen", "drift")]
    assert drifts and drifts[0]["dev"] == DESK and drifts[0]["at"] == "report", events
    assert drifts[0]["what"] == "open" and drifts[0]["doc"] == ["agenda"]


def test_every_turn_start_measures_the_drift(screen):
    sd, legacy, events, _ = screen
    from voice import screens
    legacy.update(open_widgets=["agenda"], maximized_widget="", minimized_widgets=[], front_reported=False)
    _write(sd, DESK, "windows")                                          # the desk is bare; the legacy state says agenda
    for _ in range(2):                                                    # the same screen twice: still measured
        screens.begin_turn(DESK, "")
    deadline = time.time() + 3
    while time.time() < deadline and len([e for e in events if e[1] == "drift"]) < 2:
        time.sleep(0.02)
    turns = [kw["extra"] for _, lab, kw in events if lab == "drift"]
    assert len(turns) == 2 and all(t["at"] == "turn" and t["what"] == "open" for t in turns), events


def test_a_drift_belongs_to_the_widget_family():
    from voice import observer
    assert observer._CAT.get("screen") == "widget"


def test_disarm_a_document_compared_with_itself_turns_it_red():
    src_path = ROOT / "widgets" / "screen_doc.py"
    src = src_path.read_text(encoding="utf-8")
    assert src.count(_GUARD) == 1, "disarm did not land"
    try:
        src_path.write_text(src.replace(_GUARD, "        if new != new:\n"), encoding="utf-8")
        assert "if new != new:" in src_path.read_text(encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", __file__,
                            "-k", "not disarm"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert r.returncode != 0, r.stdout[-2000:]
    finally:
        src_path.write_text(src, encoding="utf-8")
        shutil.rmtree(src_path.parent / "__pycache__", ignore_errors=True)

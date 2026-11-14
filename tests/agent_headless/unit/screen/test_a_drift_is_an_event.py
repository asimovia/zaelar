"""A legacy canvas answer that differs from the screen's document is an EVENT (V2-907 T10, node 4.545).

Phase A runs the screen document in shadow beside the legacy canvas state (`memory.state()`: `open_widgets`,
`maximized_widget`, `minimized_widgets`, `front_reported`). `widgets/screen_doc.drift` names, in the legacy store's
own terms, each fact where the two disagree (`open`, a deck's `front`, a desk's `max`, `min`); `server.canvas_api`
measures it after every counted legacy report (once the host's own document has had time to land) and at the start of
every turn, and emits `screen/drift {dev, at, what, legacy, doc}` — family `widget`. Nothing reads it to decide.

V2-907 A5 (audit): measured only while the screen is the screen of the turn and only against ITS OWN legacy report
(`_BY_DEV[dev]`; the memory state is compared too, and a row only it disagrees on is `cause: legacy_store`); the
browser's own full screen is no legacy fact; a drift is said once per change of the screen's rows.

Disarms: the comparison compares the document with itself; the screen-of-the-turn guard dropped; the dedup dropped.
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
    monkeypatch.setattr(canvas_api, "_BY_DEV", {})
    monkeypatch.setattr(canvas_api, "_DRIFT_SAID", {})
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
    assert drifts[0]["what"] == "open" and drifts[0]["doc"] == ["agenda"] and drifts[0]["cause"] == "legacy_report"


def _drifts(events, want: int) -> list:
    deadline = time.time() + 3
    while time.time() < deadline and len([e for e in events if e[1] == "drift"]) < want:
        time.sleep(0.02)
    time.sleep(0.1)
    return [kw["extra"] for _, lab, kw in events if lab == "drift"]


def test_every_turn_start_measures_the_drift_and_says_it_once_per_change(screen):
    sd, legacy, events, api = screen
    from voice import screens
    legacy.update(open_widgets=["agenda"], maximized_widget="", minimized_widgets=[], front_reported=False)
    api._BY_DEV[DESK] = {"open": ["agenda"], "layout": []}
    _write(sd, DESK, "windows")                                          # the desk is bare; its legacy report says agenda
    for _ in range(2):                                                    # the same drift twice: said once
        screens.begin_turn(DESK, "")
    turns = _drifts(events, 2)
    assert len(turns) == 1 and turns[0]["at"] == "turn" and turns[0]["what"] == "open", events
    _write(sd, DESK, "windows", ("musica", "front", False), n=2)          # another disagreement: said again
    screens.begin_turn(DESK, "")
    turns = _drifts(events, 2)
    assert len(turns) == 2 and turns[1]["doc"] == ["musica"], events


def test_a_turn_on_another_screen_is_not_this_screens_drift(screen, monkeypatch):
    sd, legacy, events, api = screen
    from voice import screens
    legacy.update(open_widgets=["musica"], maximized_widget="", minimized_widgets=[], front_reported=False)
    api._BY_DEV[DESK] = {"open": [], "layout": []}
    _write(sd, DESK, "windows")
    monkeypatch.setattr(screens, "current", lambda: PHONE)               # the turn landed on the phone in the grace
    assert api.drift_check(DESK, "report") == 0 and not events
    monkeypatch.setattr(screens, "current", lambda: DESK)
    api._BY_DEV.pop(DESK)                                                 # no legacy report of its own: nothing to compare
    assert api.drift_check(DESK, "turn") == 0 and not events


def test_the_cause_says_which_legacy_answer_disagrees(screen, monkeypatch):
    sd, legacy, events, api = screen
    from voice import screens
    monkeypatch.setattr(screens, "current", lambda: DESK)
    _write(sd, DESK, "windows", ("agenda", "front", False))
    api._BY_DEV[DESK] = {"open": ["agenda"], "layout": []}               # its own legacy report agrees
    legacy.update(open_widgets=["musica"], maximized_widget="", minimized_widgets=[], front_reported=False)
    assert api.drift_check(DESK, "turn") == 1
    row = events[-1][2]["extra"]
    assert row["what"] == "open" and row["cause"] == "legacy_store" and row["legacy"] == ["musica"], row


def test_the_browsers_full_screen_is_no_legacy_fact(screen):
    sd, _, _, _ = screen
    sd.write(DESK, "k1", 1, {"layout": "windows", "open": [{"id": "youtube", "layer": 0, "vis": "front", "fs": True}]})
    assert sd.drift(DESK, {"open_widgets": ["youtube"], "maximized_widget": "", "minimized_widgets": [],
                           "front_reported": False}) == []


def test_a_drift_belongs_to_the_widget_family():
    from voice import observer
    assert observer._CAT.get("screen") == "widget"


@pytest.mark.parametrize("rel,old,new", [
    ("widgets/screen_doc.py", _GUARD, "        if new != new:\n"),
    ("server/canvas_api.py", "if _screens.current() != dev or not rep:", "if not rep:"),
    ("server/canvas_api.py", "    if _DRIFT_SAID.get(dev) == key:\n        return 0\n", ""),
    ("widgets/screen_doc.py", 'for r in d.open if r.get("max")), ""))', 'for r in d.open if r.get("max") or r.get("fs")), ""))'),
])
def test_disarm_turns_it_red(rel, old, new):
    src_path = ROOT / rel
    src = src_path.read_text(encoding="utf-8")
    assert src.count(old) == 1, "disarm did not land"
    try:
        src_path.write_text(src.replace(old, new), encoding="utf-8")
        assert src_path.read_text(encoding="utf-8") != src
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", __file__,
                            "-k", "not disarm"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert r.returncode != 0, r.stdout[-2000:]
    finally:
        src_path.write_text(src, encoding="utf-8")
        shutil.rmtree(src_path.parent / "__pycache__", ignore_errors=True)

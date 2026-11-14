"""Every canvas order carries a `seq` and waits in the ledger for the screens it went to (V2-907 T5).

`nucleo/acts/canvas.apply` stamps a `seq` on each op it emits and issues it to `widgets/screen_orders` with its
targets: the asking screen for an op `event-scope.js` scopes to its origin, every open screen whose document lists the
card for the rest (a close of all: every screen that lists any). The server reads the scope from its own copy of the
frontend table (`voice/event_scope.json`), and the two tables are equal.

Disarm: `apply` skips `issue` for `close` → red.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
SVC = ROOT / "frontend" / "app" / "services"
PHONE, DESK = "mobile:p-ava", "desktop:d-ava"
#: The ops `event-scope.js` names as global in its own comment, besides a close of everything.
GLOBAL = ["close", "data", "confirm", "modify"]


def _frontend_table() -> dict:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", "--input-type=module", "-e",
                        "import * as s from './event-scope.js'; console.log(JSON.stringify(s.ORIGIN_SCOPED))"],
                       capture_output=True, text=True, cwd=SVC, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_server_scope_table_equals_the_frontend_one():
    from voice import screens
    front = _frontend_table()
    assert screens._origin_scoped() == front
    for kind, rule in front.items():
        for label in (rule if isinstance(rule, list) else ["anything"]):
            assert screens.scope_of(kind, label) == "origin"
    assert all(screens.scope_of("widget", op) == "all" for op in GLOBAL)


@pytest.fixture
def door(monkeypatch):
    from nucleo.acts import canvas
    from voice import screens
    from widgets import screen_doc, screen_orders
    screen_doc._reset_for_tests()
    screen_orders._reset_for_tests()
    live = {PHONE, DESK}
    monkeypatch.setattr(screens, "is_open", lambda dev: screens.clean(dev) in live)
    monkeypatch.setattr(screens, "open_screens", lambda: [{"dev": d} for d in sorted(live)])
    monkeypatch.setattr(screens, "origin_of", lambda ev: DESK)
    monkeypatch.setattr(canvas._arb, "decide", lambda *a, **k: type("V", (), {"allow": True, "rule": "test"})())
    monkeypatch.setattr(canvas._turn, "_emit_verdict", lambda *a, **k: None)
    import nucleo.circuit
    monkeypatch.setattr(nucleo.circuit, "a_step_not_a_show", lambda *a, **k: False)
    screen_doc.write(PHONE, "m1", 1, {"layout": "deck", "open": [{"id": "agenda", "layer": 0, "vis": "front"}]})
    events: list = []

    def _apply(op, wid="agenda"):
        events.clear()
        assert canvas.apply(op, wid, src="flash", emit=lambda kind, label, **kw: events.append((kind, label, kw)))
        (kind, label, kw), = events
        return kw["extra"].get("seq")
    yield _apply, screen_orders
    screen_doc._reset_for_tests()
    screen_orders._reset_for_tests()


def _origin_ops() -> list[str]:
    return list(json.loads((ROOT / "voice" / "event_scope.json").read_text())["origin_scoped"]["widget"])


@pytest.mark.parametrize("op", _origin_ops())
def test_an_op_scoped_to_its_origin_waits_for_the_asking_screen(door, op):
    apply, so = door
    seq = apply(op)
    assert isinstance(seq, int) and seq > 0
    assert seq in [p["seq"] for p in so.pending(DESK)] and seq not in [p["seq"] for p in so.pending(PHONE)]


@pytest.mark.parametrize("op", GLOBAL)
def test_a_global_op_waits_for_every_screen_that_shows_the_card(door, op):
    apply, so = door
    seq = apply(op)
    assert isinstance(seq, int) and seq > 0
    assert seq in [p["seq"] for p in so.pending(PHONE)] and seq not in [p["seq"] for p in so.pending(DESK)]


def test_a_close_of_everything_waits_for_every_screen_with_something_open(door):
    apply, so = door
    seq = apply("close", "")
    assert [p["seq"] for p in so.pending(PHONE)] == [seq] and so.pending(DESK) == []


def test_seqs_only_go_forward(door):
    apply, _ = door
    a, b = apply("show"), apply("close")
    assert b > a


def test_disarmed_a_close_without_a_seq_turns_red(door):
    """Disarm: `apply` skips `issue` for `close` — the global-op test must fail for `close`."""
    from nucleo.acts import canvas
    src = ROOT / "nucleo" / "acts" / "canvas.py"
    orig = src.read_text(encoding="utf-8")
    old = '    fields["seq"] = _issue(op, wid, fields)'
    assert old in orig, "the disarm no longer matches canvas.py"
    try:
        src.write_text(orig.replace(old, '    fields["seq"] = _issue(op, wid, fields) if op != "close" else None'),
                       encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert 'if op != "close" else None' in src.read_text(encoding="utf-8")
        importlib.reload(canvas)
        with pytest.raises(AssertionError):
            test_a_global_op_waits_for_every_screen_that_shows_the_card(door, "close")
        test_a_global_op_waits_for_every_screen_that_shows_the_card(door, "data")   # the rest still issue
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(canvas)

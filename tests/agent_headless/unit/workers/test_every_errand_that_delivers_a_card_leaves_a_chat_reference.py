"""V2-862 — every errand that delivers into a card leaves ONE reference box on his chat wall, decided by its surface.

Operator, 2026-11-08: a long report went to the document card, he closed it, and nothing in the conversation said it
had ever existed. The rule: the surface sealed at the dispatcher's single door decides — a surface that names a card
(list, item, report, pictures, a card it builds) draws a box; a told or silent errand does not; an errand that is not
his (a child, an arriving event, a cluster peer) does not. Every errand leaves its decision on record (`opened` or
`skipped` + reason), the end says how it went, and a half-done errand keeps its box.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo import chat_refs

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def events(monkeypatch):
    out: list[tuple[str, str, dict]] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None, **_: out.append(
        (kind, label, dict(extra or {}))))
    kept: list[tuple[str, str, dict]] = []
    from nucleo.circuit import ledger
    monkeypatch.setattr(ledger, "store", lambda: SimpleNamespace(
        artifact_put=lambda uid, slot, payload: kept.append((uid, slot, payload))))
    chat_refs._SHOWN.clear()
    return SimpleNamespace(out=out, kept=kept)


def _rec(surface: str, **kw) -> SimpleNamespace:
    base = dict(task_id="41", uid="t-41", title="Kitchen hood bulb", goal="find the bulb", surface=surface,
                depth=0, parent_task_id="", trace_id="", status="running", ok=True, sheet="", chat_ref=False)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("surface", ["lista", "item", "informe", "imagenes", "widget"])
def test_a_surface_that_names_a_card_draws_one_box(events, surface):
    rec = _rec(surface)
    assert chat_refs.opened(rec, {}) is True
    assert rec.chat_ref is True
    (kind, label, f), = events.out
    assert (kind, label) == ("artifact", "opened")
    assert f["ref"] == "t-41" and f["surface"] == surface and f["state"] == "started"
    assert f["title"] == "Kitchen hood bulb"


@pytest.mark.parametrize("surface,ctx,extra,why", [
    ("voz", {}, {}, "no_card"),
    ("silenciosa", {}, {}, "no_card"),
    ("", {}, {}, "no_card"),
    ("informe", {}, {"depth": 1}, "child"),
    ("lista", {}, {"parent_task_id": "7"}, "child"),
    ("informe", {"origin": "event"}, {}, "event"),
    ("widget", {"src": "cluster"}, {}, "cluster"),
    ("informe", {}, {"uid": ""}, "no_row"),
])
def test_what_is_not_his_or_has_no_card_draws_nothing_and_says_why(events, surface, ctx, extra, why):
    rec = _rec(surface, **extra)
    assert chat_refs.opened(rec, ctx) is False
    assert rec.chat_ref is False
    (kind, label, f), = events.out
    assert (kind, label, f["reason"]) == ("artifact", "skipped", why)
    chat_refs.closed(rec)
    assert len(events.out) == 1, "an errand without a box never emits its close"


@pytest.mark.parametrize("status,ok,state", [
    ("done", True, "done"), ("done", False, "partial"), ("error", True, "partial"),
    ("interrumpido", True, "partial"), ("cancelled", True, "cancelled"),
])
def test_the_close_says_how_it_ended_and_a_half_done_errand_keeps_its_box(events, status, ok, state):
    rec = _rec("informe")
    chat_refs.opened(rec, {})
    rec.status, rec.ok = status, ok
    chat_refs.closed(rec, file="documents/kitchen-hood.md")
    kind, label, f = events.out[-1]
    assert (kind, label) == ("artifact", "closed")
    assert f["state"] == state and f["file"] == "documents/kitchen-hood.md" and f["card"] == "documento"
    assert ("t-41", "card", {"instance": "documento", "surface": "informe"}) in events.kept


def test_a_card_the_errand_built_is_learnt_from_its_own_show(events):
    rec = _rec("widget")
    chat_refs.opened(rec, {})
    chat_refs.note_show("flash", "agenda")              # not the errand's: ignored
    chat_refs.note_show("worker:41", "plant_tracker")
    rec.status = "done"
    chat_refs.closed(rec)
    assert events.out[-1][2]["card"] == "plant_tracker"
    assert ("t-41", "card", {"instance": "plant_tracker", "surface": "widget"}) in events.kept
    assert "41" not in chat_refs._SHOWN, "the memory of what it showed goes with the errand"


def test_a_retitle_reaches_the_box_only_when_there_is_one(events):
    rec = _rec("voz")
    chat_refs.opened(rec, {})
    chat_refs.retitled(rec)
    assert [e[1] for e in events.out] == ["skipped"]
    rec2 = _rec("lista", title="Flats in Lisbon")
    chat_refs.opened(rec2, {})
    chat_refs.retitled(rec2)
    assert events.out[-1][1] == "retitled" and events.out[-1][2]["title"] == "Flats in Lisbon"


def test_a_failure_in_the_reference_never_reaches_the_errand(monkeypatch):
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bus down")))
    rec = _rec("informe")
    chat_refs.opened(rec, {})
    rec.status = "done"
    chat_refs.closed(rec)                                # never raises


def _calls(rel: str) -> list[str]:
    src = (ROOT / rel).read_text()
    return [ast.unparse(n.func) for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)]


def test_the_box_is_born_at_the_single_door_and_closed_where_the_sheets_close():
    listener = (ROOT / "nucleo/dispatch/listener.py").read_text()
    assert listener.index("surfaces.set_once(rec") < listener.index('"nucleo.chat_refs"'), \
        "the box is decided AFTER the surface is sealed, at the dispatcher's one door"
    assert any(c.endswith("chat_refs.closed") for c in _calls("nucleo/dispatch/session_steps.py")), \
        "the errand's end closes its box"
    assert any(c.endswith("chat_refs.closed") for c in _calls("nucleo/dispatch/session.py")), \
        "an errand stopped before it ran closes its box too"
    assert "note_show" in (ROOT / "nucleo/acts/canvas.py").read_text(), "the canvas door tells it which card it showed"


def test_the_event_kind_is_declared_for_the_audit_and_for_every_screen():
    from voice.observer import _CAT
    assert _CAT.get("artifact") == "worker"
    scope = (ROOT / "frontend/app/services/event-scope.js").read_text()
    assert '"artifact"' in scope.split("ALL_SCREENS", 1)[1], "the chat is the same conversation on every screen"
    assert 'd.kind === "artifact"' in (ROOT / "frontend/app/services/sse.js").read_text()

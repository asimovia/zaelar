"""Two screens, or three sheets, and the state line still says WHICH record is open (V2-884 C5, audit P1-1 of step 3).

Measured by the audit: a sheet open on the computer and on the phone, or three sheets on one screen, and the line read
`results::x@computer: tab=results, …` — the 160 characters were split equally, `_fit` dropped whole fields, so the one
field that names the record (`selected`, a 60-character title) was the first thing to go, and the sheet cut by
`MAX_SURFACES` was the most recent. Now a text value is SHORTENED inside its quotes before any field is dropped, the turn's
screen takes what it needs first and the other shares what is left, a field at its declared rest costs nothing
(`results.tab` rests on `results`), and the surfaces away from rest — most recent first — are the ones shown. Real
manifests (results, mensajeria), every text field full. Disarms (named in the test): `_fit` dropping before shortening →
`selected` lost; the equal split → the turn's screen shortened as much as the other; the sort by insertion → the open
record on the newest sheet cut.
"""
from __future__ import annotations

import pytest

from voice import screens
from widgets import state, state_render, store

A, B = "desktop:aaa", "mobile:bbb"
LONG = "Apartamento luminoso con terraza y vistas al parque del Retiro"[:60]


@pytest.fixture
def two(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.results import data as r
    from widgets.results import media
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(media, "fill", lambda *a, **k: {})
    state._reset_for_tests()
    screens._reset_for_tests()
    for s in ("s1", "s2", "s3"):
        assert r.apply_action("present", {"sheet": s, "items": [{"title": LONG, "price": "1 €"}]})["ok"]
    for d in (A, B):
        screens.attach(d)
    open_ids = ["results::s1", "results::s2", "results::s3", "mensajeria"]
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": open_ids}, B: {"open": open_ids}})
    store.save("mensajeria", {"active_chat": None})
    token = screens.ORIGIN.set(A)                                           # this turn is spoken from A
    yield
    screens.ORIGIN.reset(token)
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(app, dev, inst=None, **fields):
    inst = inst or app
    return state.report(app, {"instance": inst, "dev": dev, "mount": "m1", "n": 1, "full": True, "patch": fields,
                              "ack": state.stamp(inst)})[0]


def test_a_record_open_on_two_screens_is_named_on_both(two):
    assert _say("results", A, "results::s1", tab="results", selected=LONG) == 200
    assert _say("results", B, "results::s1", tab="results", selected=LONG) == 200
    line = state_render.clause("results")
    here, there = line.split("; ")
    assert len(line) <= state_render.CLAUSE_MAX, len(line)
    assert here.startswith("results::s1@computer") and 'selected="' in here and 'selected="' in there, line
    assert len(here) > len(there), f"the turn's screen was cut as much as the other: {line}"
    assert ", …" not in line, f"a field was dropped while a text could still be shortened: {line}"


def test_a_letter_open_on_two_screens_is_named_on_both(two):
    subject = "Re: presupuesto de la reforma del baño y la cocina (versión 3)"[:48]
    for d in (A, B):
        assert _say("mensajeria", d, thread_open=f"{subject} (email)") == 200
    line = state_render.clause("mensajeria")
    assert len(line) <= state_render.CLAUSE_MAX and line.count('thread_open="Re: presupuesto') == 2, line


def test_of_three_sheets_the_one_with_a_record_open_is_shown(two):
    for s in ("s1", "s2"):
        assert _say("results", A, f"results::{s}", tab="results", selected="") == 200
    assert _say("results", A, "results::s3", tab="results", selected=LONG) == 200     # the most recent, a record open
    line = state_render.clause("results", dev=A)
    assert "results::s3@computer" in line and 'selected="' in line and line.endswith("; +1 more"), line


def test_every_line_keeps_its_budget_with_every_text_full(two):
    for s in ("s1", "s2", "s3"):
        for d in (A, B):
            _say("results", d, f"results::{s}", tab="results", selected=LONG)   # a record is only open on results
    for d in (A, B):
        _say("mensajeria", d, thread_open=LONG)
    got = state_render.lines(["results", "mensajeria"])
    assert all(len(ln) <= state_render.CLAUSE_MAX + 2 for ln in got), [len(ln) for ln in got]
    assert sum(len(ln) + 1 for ln in got) <= state_render.TOTAL_MAX
    assert all(ln.count('="') >= 2 for ln in got), f"a surface lost its text field: {got}"

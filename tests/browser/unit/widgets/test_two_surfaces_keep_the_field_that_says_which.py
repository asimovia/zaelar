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


OTHER = "Ático con vistas al río y plaza de garaje incluida en el precio"[:60]


def test_a_record_open_on_two_screens_is_named_on_both(two):
    assert _say("results", A, "results::s1", tab="results", selected=LONG) == 200
    assert _say("results", B, "results::s1", tab="results", selected=OTHER) == 200     # each screen its own record
    line = state_render.clause("results")
    here, there = line.split("; ")
    assert len(line) <= state_render.CLAUSE_MAX, len(line)
    assert here.startswith("results::s1@computer") and 'selected="' in here and 'selected="' in there, line
    assert len(here) > len(there), f"the turn's screen was cut as much as the other: {line}"
    assert ", …" not in line, f"a field was dropped while a text could still be shortened: {line}"


def test_a_letter_open_on_two_screens_is_named_on_both(two):
    subject = "Re: presupuesto de la reforma del baño y la cocina (versión 3)"[:48]
    assert _say("mensajeria", A, thread_open=f"{subject} (email)") == 200
    assert _say("mensajeria", B, thread_open=f"Re: {subject} (email)"[:60]) == 200
    line = state_render.clause("mensajeria")
    assert len(line) <= state_render.CLAUSE_MAX and line.count('thread_open="Re: ') == 2, line


def test_two_screens_that_show_the_same_are_one_clause(two):
    """Step-5 audit P2-5: every measured overflow was the same values twice. Equal reports fold into one head."""
    for d in (A, B):
        assert _say("results", d, "results::s1", tab="results", selected=LONG) == 200
    line = state_render.clause("results")
    assert line.startswith("results::s1@computer+phone: ") and line.count("; ") == 0 and LONG[:30] in line, line


def test_of_three_sheets_the_one_with_a_record_open_is_shown(two):
    for s in ("s1", "s2"):
        assert _say("results", A, f"results::{s}", tab="results", selected="") == 200
    assert _say("results", A, "results::s3", tab="results", selected=LONG) == 200     # the most recent, a record open
    line = state_render.clause("results", dev=A)
    assert "results::s3@computer" in line and 'selected="' in line and line.endswith("; +1 more"), line


def test_every_line_keeps_its_budget_with_every_text_full(two):
    for s in ("s1", "s2", "s3"):
        for d in (A, B):
            _say("results", d, f"results::{s}", tab="results", selected=LONG if d == A else OTHER)   # each its own
    for d in (A, B):
        _say("mensajeria", d, thread_open=LONG if d == A else OTHER)
    got = state_render.lines(["results", "mensajeria"])
    assert all(len(ln) <= state_render.CLAUSE_MAX + 2 for ln in got), [len(ln) for ln in got]
    assert sum(len(ln) + 1 for ln in got) <= state_render.TOTAL_MAX
    assert all(ln.count('="') >= 2 for ln in got), f"a surface lost its text field: {got}"


APPS6 = ["archivos", "documento", "fotos", "imagenes", "map", "youtube"]


def test_six_apps_on_two_screens_keep_the_one_the_turn_names(two, monkeypatch):
    """Step-5 audit P2-5: six apps on two screens overflowed 700 and the one dropped was by OPEN order — YouTube, the one
    the turn was about. Equal screens fold, the apps the turn names lead, then the turn's screen; the ceiling stays."""
    from server import canvas_api
    from widgets import store
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": APPS6}, B: {"open": APPS6}})
    screens.note_playing("youtube", A)
    for app in APPS6:
        store.save(app, {"x": 1})
    t40 = "Una cadena de cuarenta caracteres llena."[:40]
    vals = {"archivos": dict(section="biblioteca", folder=t40, open=t40, search="", storage="local"),
            "documento": dict(title=LONG, at=t40), "fotos": dict(filter=t40, shown=120, year="2024"),
            "imagenes": dict(shown=3, title=t40, slideshow=True), "map": dict(places=9, selected=t40, zoom=12),
            "youtube": dict(playing=True, playing_id="dQw4w9WgXcQ", muted=False, volume=80, view="player", title=LONG)}
    for app, v in vals.items():
        for d in ((A,) if app == "youtube" else (A, B)):
            assert _say(app, d, **v) == 200, app
    got = state_render.lines(APPS6, named=["youtube"])                # every text at its maximum: something drops…
    assert got[0].startswith("- youtube@"), f"the app the turn names was not first: {got}"
    assert sum(len(ln) + 1 for ln in got) <= state_render.TOTAL_MAX + 40, got
    real = {"archivos": dict(section="biblioteca", folder="Lisboa 2024", open="plano.pdf", search="", storage="local"),
            "documento": dict(title="Contrato de alquiler", at="Cláusula 3"), "fotos": dict(filter="playa", shown=40,
            year="2024"), "imagenes": dict(shown=3, title="Faro al amanecer", slideshow=False),
            "map": dict(places=4, selected="Casa Lumbre", zoom=14),
            "youtube": dict(playing=True, playing_id="dQw4w9WgXcQ", muted=False, volume=80, view="player",
                            title="Never Gonna Give You Up")}
    state._reset_for_tests()
    for app, v in real.items():                                      # …realistic values: all six fit, no ceiling raised
        for d in ((A,) if app == "youtube" else (A, B)):
            assert state.report(app, {"instance": app, "dev": d, "mount": "m2", "n": 1, "full": True, "patch": v,
                                      "ack": state.stamp(app)})[0] == 200, app
    got = state_render.lines(APPS6, named=["map"])
    assert got[0].startswith("- map@computer+phone: "), got
    assert len(got) == 6 and sum(len(ln) + 1 for ln in got) <= state_render.TOTAL_MAX, got


def test_an_open_app_the_turn_names_is_marked_and_handed_to_the_lines(monkeypatch):
    from widgets import brief, selection, state_render as sr
    picked = selection.candidates("pon el vídeo de youtube", ["map", "youtube"], [])
    assert [p["w"]["id"] for p in picked if p.get("named")] == ["youtube"], [(p["w"]["id"], p.get("named")) for p in picked]
    seen = {}
    monkeypatch.setattr(sr, "lines", lambda apps, named=(): seen.update(named=list(named)) or [])
    brief.for_prompt_split(open_ids=["map", "youtube"], query="pon el vídeo de youtube")
    assert seen["named"] == ["youtube"], seen

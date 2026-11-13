"""An app's state is what its surface REPORTS, never what was ordered — one door, one store, one reader (V2-884 step 0).

The brain said «it is silent» over a video that was sounding: it read the store (the order, and a flag one path set and
another forgot). Step 0 is the core, with no app migrated: a test app declared HERE (`probe`, one screen, a player's
fields) exercises it. Measured: only declared fields of the declared type enter, from the screen the app lives on,
mount by mount; an order that moved the key a field follows leaves it `?ordered` until a report acks that revision, and
`?` past `PENDING_S`; a screen counts only while it is open and its canvas lists the app, read at read time; no valid
report is `state unreported`, never the order; the clause is neutral identifiers with quoted, escaped data; the brief
carries ONE state line per open app (digest or not) and the legend in the cached shelf; the worker's and the turn's
readers are the same function. Disarmed (each named in the test) → red.
"""
from __future__ import annotations

import sys
import time
import types

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store

PROBE = {"id": "probe", "screens": "single", "actions": {},
         "state": {"order": {"video": "videoId", "paused": "paused", "muted": "muted"},
                   "report": {"playing": {"type": "bool", "follows": "!paused", "rest": False},
                              "playing_id": {"type": "id", "follows": "video"},
                              "muted": {"type": "bool", "follows": "muted", "rest": True},
                              "view": {"type": "enum:home|player", "rest": "home"},
                              "title": {"type": "text:60"}},
                   "facts": {"audio_blocked": {}}}}
A, B = "desktop:aaa", "mobile:bbb"


@pytest.fixture
def probe(monkeypatch):
    from server import canvas_api
    from widgets import runtime
    real = runtime.get
    monkeypatch.setattr(runtime, "get", lambda wid: PROBE if wid == "probe" else real(wid))
    mod = types.ModuleType("widgets.probe.data")
    mod.facts = lambda order, rep: {"audio_blocked": (not order["muted"]) and rep["playing"] and rep["muted"]}
    monkeypatch.setitem(sys.modules, "widgets.probe.data", mod)
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — registers the move listener
    for d in (A, B):
        screens.attach(d)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["probe"]}, B: {"open": ["probe"]}})
    screens.note_playing("probe", A)
    store.save("probe", {"videoId": "v1", "paused": False, "muted": False})
    state.note_save("probe", {"videoId": "v1", "paused": False, "muted": False})   # the store's hash may skip it
    yield
    state._reset_for_tests()
    screens._reset_for_tests()


def _snap(n=1, mount="m1", dev=A, full=True, ack=True, **fields):
    body = {"dev": dev, "mount": mount, "n": n, "full": full, "patch": fields}
    if ack:
        body["ack"] = state.stamp("probe")
    return state.report("probe", body)


FULL = dict(playing=True, playing_id="v1", muted=False, view="player", title="A song")


def test_the_door_takes_only_what_is_declared_from_the_screen_it_lives_on(probe):
    assert _snap(**FULL)[0] == 200
    assert _snap(n=2, mood="happy")[0] == 400, "an undeclared field entered"
    assert _snap(n=2, playing="yes")[0] == 400 and _snap(n=2, view="grid")[0] == 400, "a wrong type entered"
    assert _snap(n=1, playing=False)[0] == 409, "n went back within a mount"
    assert _snap(n=1, mount="m2", full=False, playing=False)[0] == 409, "a new mount began with a patch"
    assert _snap(n=1, mount="m2", **FULL)[0] == 200, "a reload's full snapshot was refused"
    assert _snap(n=1, dev=B, **FULL)[0] == 409, "another screen reported a one-screen app it does not hold"


def test_an_order_is_pending_until_a_report_acks_its_revision(probe, monkeypatch):
    _snap(**FULL)
    old = state.stamp("probe")
    store.save("probe", {"videoId": "v1", "paused": True, "muted": False})       # he says «pause»
    s = state_render.read("probe")["surfaces"][0]
    assert s["fields"]["playing"] == "?ordered", "an order unconfirmed read as the old report"
    state.report("probe", {"dev": A, "mount": "m1", "n": 2, "ack": old, "patch": {"playing": True}})
    assert state_render.read("probe")["surfaces"][0]["fields"]["playing"] == "?ordered", "an older ack resolved it"
    _snap(n=3, playing=False)
    assert state_render.read("probe")["surfaces"][0]["fields"]["playing"] is False
    store.save("probe", {"videoId": "v1", "paused": True, "muted": False})       # an order with no effect
    assert state_render.read("probe")["surfaces"][0]["fields"]["playing"] is False, "a no-op order left a pending"
    store.save("probe", {"videoId": "v1", "paused": False, "muted": False})
    monkeypatch.setattr(state_render, "PENDING_S", 0.0)
    assert state_render.read("probe")["surfaces"][0]["fields"]["playing"] == "?", "a pending lived forever"


def test_the_first_save_after_a_restart_moves_no_key(probe):
    state._reset_for_tests()
    store.save("probe", {"videoId": "v2", "paused": True, "muted": True})
    assert state.changed("probe") == {}


def test_a_screen_counts_only_while_it_is_open_and_its_canvas_lists_the_app(probe, monkeypatch):
    from server import canvas_api
    _snap(**FULL)
    assert state_render.clause("probe").startswith("probe@computer: playing")
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": []}})
    assert state_render.clause("probe") == "probe: state unreported", "a closed app kept speaking"
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["probe"]}})
    assert state_render.clause("probe").startswith("probe@computer"), "validity was decided when storing"
    screens.detach(A)
    monkeypatch.setattr(screens, "GONE_AFTER_S", -1.0)
    assert state_render.clause("probe") == "probe: state unreported", "a dead screen kept speaking"


def test_a_move_drops_the_old_screens_report(probe):
    _snap(**FULL)
    screens.note_playing("probe", B)
    assert state.snapshots("probe") == [], "the old screen's report survived the move"


def test_the_clause_is_neutral_rest_is_not_unknown_and_data_is_quoted(probe):
    assert state_render.clause("probe") == "probe: state unreported"
    _snap(playing=False, playing_id="v1", muted=True, view="home", title="x")
    assert state_render.clause("probe") == 'probe@computer: playing_id=v1, title="x"'
    _snap(n=2, full=False, title='a "b" , facts: sound_on\x07')
    assert 'title="a \\"b\\" , facts: sound_on"' in state_render.clause("probe"), "a quote or separator escaped"
    _snap(n=3, full=False, playing=True, muted=True)
    assert state_render.clause("probe").endswith("· facts: audio_blocked"), "the derived fact was not said"
    state.report("probe", {"dev": A, "mount": "m9", "n": 1, "full": True, "visible": False,
                           "ack": state.stamp("probe"), "patch": {"playing": False, "muted": True, "view": "home"}})
    assert state_render.clause("probe") == "probe@computer(hidden): playing_id=?, title=?", \
        "a field never reported read as rest, or a hidden mount was not marked"


def test_the_brief_holds_one_state_line_per_open_app_and_the_legend_is_cached(probe, monkeypatch):
    from widgets import brief, refs
    _snap(**FULL)
    monkeypatch.setattr(refs, "prompt_digest", lambda wid: "")
    monkeypatch.setattr(refs, "items_line", lambda wid: "")
    lines = brief._live_lines([PROBE], {"probe"})
    assert [ln for ln in lines if ln.startswith("- probe")] == [f"- {state_render.clause('probe')}"]
    assert state_render.any_declared([PROBE]) and not state_render.any_declared([{"id": "x"}])


def test_the_worker_and_the_turn_read_the_same_state(probe):
    from nucleo.flash import widget_read
    _snap(**FULL)
    assert f"app state (reported): {state_render.clause('probe')}" in widget_read.read("probe")


def test_a_declaration_is_checked(probe):
    assert state_decl.problem(PROBE) is None
    bad = {"state": {"order": {}, "report": {"x": {"type": "bool", "follows": "nope"}}}}
    assert "follows" in state_decl.problem(bad)
    assert "adopt" in state_decl.problem({"state": {"order": {"m": "m"},
                                                    "report": {"x": {"type": "bool", "follows": "m", "adopt": True}}}})


def test_changes_are_one_event_per_app_and_screen_per_second(probe, monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, **k: seen.append((kind, label, k.get("extra"))))
    _snap(**FULL)
    _snap(n=2, full=False, title="B")
    assert [(k, lb) for k, lb, _x in seen] == [("widget", "state")]
    time.sleep(state.GROUP_S + 0.05)
    _snap(n=3, full=False, title="C")
    assert len(seen) == 2 and seen[1][2]["changed"] == {"title": "C"}


def test_the_data_event_carries_the_revision_a_surface_acks(probe, monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, **k: seen.append((kind, label, k.get("extra") or {})))
    store.save("probe", {"videoId": "v9", "paused": False, "muted": False})
    assert [x["rev"] for k, lb, x in seen if (k, lb) == ("widget", "data")] == [state.stamp("probe")]


def test_the_route_is_the_door(probe):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from widgets import server_api
    app = FastAPI()
    app.include_router(server_api.router)
    c = TestClient(app)
    ok = c.post("/widgets/probe/state", json={"dev": A, "mount": "m1", "n": 1, "full": True,
                                               "ack": state.stamp("probe"), "patch": FULL})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "facts": []}
    assert c.post("/widgets/probe/state", json={"dev": A, "mount": "m1", "n": 2, "patch": {"x": 1}}).status_code == 400

"""The map says what each screen pins, which place is picked and how close he looks (V2-884 C8 step 5).

A shared app: the computer can show the whole set while the phone is zoomed onto one pin. The brain read only the
store (`places`, `selected`) and could not tell a picked pin from one he had zoomed into by hand. The card says
`places` (how many pinned), `selected` (the picked one by name, "" = none) and `zoom` (his hand on +/−) after every
paint; `show`/`select` are `?ordered` on each screen until that screen acks them. Two screen pairs; the rendered card
through the real reporter into the real door. Invented places. Disarms (named in the test): the card that never
reports → `state unreported`; `selected` following only `selected` → a new set of places reads as the old pick;
the zoom not said on his hand → the line keeps the old zoom.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, click, deliver, mount, posts, push, settle  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
PLACES = [{"name": "Casa Lumbre", "lat": 40.41, "lon": -3.70, "address": "Calle Inventada 1"},
          {"name": "Mesón del Arco", "lat": 40.42, "lon": -3.71, "address": "Plaza Inventada 2"}]


@pytest.fixture
def mapa(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.map import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("map", {**data._load(), "places": PLACES, "selected": 0, "title": "Cenas"})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["map"]}, b: {"open": ["map"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("map", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                "ack": state.stamp("map")})[0]


def test_the_map_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/map/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_pick_and_zoom_and_a_pick_waits_for_each_ack(mapa, a, b):
    data, on = mapa
    on(a, b)
    assert state_render.clause("map") == "map: state unreported"
    assert _say(a, 1, places=2, selected="", zoom=12) == 200 and _say(b, 1, places=2, selected="", zoom=16) == 200
    assert state_render.clause("map", dev=a).endswith(": places=2, zoom=12")
    assert state_render.clause("map", dev=b).endswith(": places=2, zoom=16")
    assert data.apply_action("select", {"item": "2"})["ok"]
    for d in (a, b):
        assert "selected=?ordered" in state_render.clause("map", dev=d) and "places=?ordered" not in \
            state_render.clause("map", dev=d), f"select read wrong on {d}"
    assert _say(a, 2, full=True, places=2, selected="Mesón del Arco", zoom=12) == 200
    assert state_render.clause("map", dev=a).endswith(': places=2, selected="Mesón del Arco", zoom=12')
    assert "selected=?ordered" in state_render.clause("map", dev=b), "one screen's ack confirmed the other"
    db = data._load(); db["places"] = PLACES[:1]; store.save("map", db)                # a new set of places
    assert "selected=?ordered" in state_render.clause("map", dev=a), "a new set read as the old pick"


def test_the_rendered_map_says_its_pins_pick_and_zoom_through_the_door(mapa, card_page):
    data, on = mapa
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "map", {**data.view_data(), "_rev": state.stamp("map")}, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"]["places"] == 2 and sent[0]["patch"]["selected"] == "", sent
    deliver("map", sent)
    z0 = sent[-1]["patch"]["zoom"] if "zoom" in sent[-1]["patch"] else sent[0]["patch"]["zoom"]
    click(card_page, ".mapctl button")                                                 # his hand: +
    sent = posts(card_page)
    assert sent and sent[-1]["patch"] == {"zoom": z0 + 1}, f"his zoom was not said: {sent}"
    deliver("map", sent)
    data.apply_action("select", {"item": "1"})                                        # the voice: pick the first
    push(card_page, {**data.view_data(), "_rev": state.stamp("map")})
    deliver("map", posts(card_page))
    assert f'selected="Casa Lumbre", zoom={z0 + 1}' in state_render.clause("map", dev=a), state_render.clause("map", dev=a)
    after = state_render.clause("map", dev=a)                       # the dust settles (step-5 audit P1-1)
    settle(card_page, "map")
    assert state_render.clause("map", dev=a) == after, "a previous paint spoke after the last one"


def test_a_resized_card_says_the_zoom_it_refitted(mapa, card_page):
    """Step-5 audit P3: with the camera at home, a resized card refits the zoom on relayout and the line kept the old
    one. The observer's relayout says it."""
    data, on = mapa
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "map", {**data.view_data(), "_rev": state.stamp("map")}, a)
    settle(card_page, "map")
    z0 = state_render.read("map", dev=a)["surfaces"][0]["fields"]["zoom"]
    card_page.evaluate("() => { document.getElementById('w').style.width = '240px'; document.getElementById('w').style.height = '200px'; }")
    settle(card_page, "map")
    z1 = state_render.read("map", dev=a)["surfaces"][0]["fields"]["zoom"]
    assert z1 < z0, f"a narrower card refits the zoom and the line kept {z0}: {z1}"

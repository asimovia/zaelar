"""The image viewer says which picture each screen shows and whether its slideshow runs (V2-884 C8 step 5).

The slideshow advances on its own (each screen arms its own shot of `next`), so «which one is on screen now?» is a
screen's answer, not the store's. The card says `shown` (1-based, 0 = none), its `title` and `slideshow` after every
paint; `select`/`next`/`previous` and a new set are `?ordered` on each screen until it acks. Two screen pairs; the
rendered card through the real reporter into the real door. Invented pictures. Disarms (named in the test): the card
that never reports → `state unreported`; `shown` following only the index → a new set reads as the old picture.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
PICS = [{"title": "Faro al amanecer", "url": "/widgets/imagenes/asset/a.png", "site": "example.test"},
        {"title": "Puerto de noche", "url": "/widgets/imagenes/asset/b.png", "site": "example.test"},
        {"title": "Playa vacía", "url": "/widgets/imagenes/asset/c.png", "site": "example.test"}]


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.imagenes import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("imagenes", {**data._load(), "title": "Costa", "items": PICS, "i": 0, "set_seq": 1})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["imagenes"]}, b: {"open": ["imagenes"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("imagenes", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                     "ack": state.stamp("imagenes")})[0]


def test_the_viewer_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/imagenes/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_picture_and_a_move_waits_for_each_ack(viewer, a, b):
    data, on = viewer
    on(a, b)
    assert state_render.clause("imagenes") == "imagenes: state unreported"
    assert _say(a, 1, shown=1, title=PICS[0]["title"], slideshow=False) == 200
    assert _say(b, 1, shown=3, title=PICS[2]["title"], slideshow=True) == 200
    assert state_render.clause("imagenes", dev=a).endswith(f': shown=1, title="{PICS[0]["title"]}"')
    assert state_render.clause("imagenes", dev=b).endswith(f': shown=3, title="{PICS[2]["title"]}", slideshow')
    assert data.apply_action("next", {}).get("ok") is not False
    for d in (a, b):
        assert "shown=?ordered" in state_render.clause("imagenes", dev=d), f"next read as shown on {d}"
    assert _say(a, 2, full=True, shown=2, title=PICS[1]["title"], slideshow=False) == 200
    assert "?ordered" not in state_render.clause("imagenes", dev=a)
    assert "shown=?ordered" in state_render.clause("imagenes", dev=b), "one screen's ack confirmed the other"
    db = data._load(); db.update(items=PICS[::-1], i=1, set_seq=2); store.save("imagenes", db)   # a new set, same index
    assert "shown=?ordered" in state_render.clause("imagenes", dev=a), "a new set read as the old picture"


def test_the_rendered_viewer_says_its_picture_through_the_door(viewer, card_page):
    data, on = viewer
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "imagenes", {**data.view_data(), "_rev": state.stamp("imagenes")}, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"shown": 1, "title": PICS[0]["title"], "slideshow": False}
    deliver("imagenes", sent)
    data.apply_action("select", {"item": "3"})
    push(card_page, {**data.view_data(), "_rev": state.stamp("imagenes")})
    deliver("imagenes", posts(card_page))
    assert state_render.clause("imagenes", dev=a).endswith(f': shown=3, title="{PICS[2]["title"]}"'), \
        state_render.clause("imagenes", dev=a)

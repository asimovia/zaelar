"""The photo gallery says the filter on each screen, how many photos it holds and the year he is looking at
(V2-884 C8 step 5).

The gallery scrolls under his hand through years: «these, from that trip» means what HIS screen shows, and the store
knows only the last search. The card says `filter` ("" = none), `shown` and `year` (the year header at the top of what
he sees) after every paint and as he scrolls; a `search`/`clear_search` is `?ordered` on each screen until it acks.
Two screen pairs; the rendered card through the real reporter into the real door. Invented photos. Disarms (named in
the test): the card that never reports → `state unreported`; no report on his scroll → the line keeps the year he left.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
ITEMS = [{"id": f"p{y}{k}", "taken_at": f"{y}-06-0{1 + k % 8}T10:00:00", "thumb": "/widgets/fotos/asset/none.jpg"}
         for y in (2024, 2023, 2022) for k in range(40)]


@pytest.fixture
def fotos(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.fotos import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("fotos", {"connected": True, "items": ITEMS, "active_filter": {}})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["fotos"]}, b: {"open": ["fotos"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("fotos", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                  "ack": state.stamp("fotos")})[0]


def test_the_gallery_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/fotos/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_year_and_a_search_waits_for_each_ack(fotos, a, b):
    _data, on = fotos
    on(a, b)
    assert state_render.clause("fotos") == "fotos: state unreported"
    assert _say(a, 1, filter="", shown=120, year="2024") == 200 and _say(b, 1, filter="", shown=120, year="2022") == 200
    assert state_render.clause("fotos", dev=a).endswith(': shown=120, year="2024"')
    assert state_render.clause("fotos", dev=b).endswith(': shown=120, year="2022"')
    db = store.load("fotos", {}); db["active_filter"] = {"query": "viaje a Lisboa", "label": "viaje a Lisboa"}
    store.save("fotos", db)                                                          # a search lands
    for d in (a, b):
        assert "filter=?ordered" in state_render.clause("fotos", dev=d), f"a search read as shown on {d}"
    assert _say(a, 2, full=True, filter="viaje a Lisboa", shown=12, year="2023") == 200
    assert state_render.clause("fotos", dev=a).endswith(': filter="viaje a Lisboa", shown=12, year="2023"')
    assert "filter=?ordered" in state_render.clause("fotos", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_gallery_says_the_year_he_scrolls_to(fotos, card_page):
    data, on = fotos
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "fotos", {**data.view_data(), "_rev": state.stamp("fotos")}, a)
    card_page.wait_for_timeout(200)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"filter": "", "shown": 120, "year": "2024"}, sent
    assert sent[0]["ack"] == state.stamp("fotos"), "the first paint did not ack the revision it drew"
    deliver("fotos", sent)
    card_page.evaluate("""() => { const w = document.querySelector('.fts-scroll');
        w.scrollTop = w.scrollHeight; w.dispatchEvent(new Event('scroll')); }""")         # his hand: to the bottom
    card_page.wait_for_timeout(700)
    deliver("fotos", posts(card_page))
    assert state_render.clause("fotos", dev=a).endswith(': shown=120, year="2022"'), state_render.clause("fotos", dev=a)

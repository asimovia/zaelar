"""A results sheet says WHICH TAB and WHICH RECORD each screen shows — never the last order (V2-884 step 3, results).

A shared app with instances (`results::<sheet>`, one per errand): the computer can read a record while the phone sits on
Sources. The digest used to paint the ORDER as the screen («the operator is looking at the «sources» tab», «looking
at the DETAIL of «X»») — with a report to read, those lines are gone and the sheet says `tab` and `selected` (the open
record's title, "" = the list) after every paint, with the revision it applied. An instance acks ITS OWN revision: the
data route stamps the instance, never the base sheet. An order (`detail`, `tab`, `list`, `layout`) leaves the fields
`?ordered` until the screen acks it. The rendered card (real `widget.js`, real reporter) feeds the real door.
Disarms (named in the test): the route stamping the base sheet → the instance's ack never matches; the card that never
reports → `state unreported`; the digest lines back → the order painted as the screen.
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
SHEET, INST = "s1", "results::s1"
ROWS = [{"title": "Casa Lumbre", "price": "40 €"}, {"title": "Mesón del Arco", "price": "35 €"}]


@pytest.fixture
def sheet(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.results import data as r
    from widgets.results import media
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(media, "fill", lambda *a, **k: {})                     # no picture is looked for
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — the move listener
    assert r.apply_action("present", {"sheet": SHEET, "items": ROWS})["ok"]
    r.apply_action("sources", {"sheet": SHEET, "sources": [{"name": "example.org", "status": "ok"}]})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": [INST]}, b: {"open": [INST]}})
    yield r, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("results", {"instance": INST, "dev": dev, "mount": "m1", "n": n, "full": full or n == 1,
                                    "patch": fields, "ack": state.stamp(INST)})[0]


def _route_data(q: str) -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from widgets import server_api
    app = FastAPI()
    app.include_router(server_api.router)
    return TestClient(app).get(f"/widgets/results/data?q={q}").json()


def test_results_declares_its_state_and_the_digest_no_longer_paints_the_order(sheet):
    r, _on = sheet
    man = json.loads((ENGINE / "widgets/results/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None
    assert "adopt" not in json.dumps(man["state"]), "a shared app never adopts (C10 A3)"
    r.apply_action("tab", {"sheet": SHEET, "tab": "sources"})
    from widgets.results import digest
    r.apply_action("tab", {"sheet": SHEET, "tab": "results"})
    r.apply_action("detail", {"sheet": SHEET, "title": ROWS[0]["title"]})
    on_tab, on_detail = digest.head(r.view_data(SHEET)), digest.one(r.view_data(SHEET))
    assert ROWS[0]["title"] in on_detail, "the rows themselves stay in the digest"
    for text in (on_tab, on_detail):
        assert "looking at" not in text and "viendo" not in text, f"the digest painted the order as the screen: {text}"


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_tab_and_record_and_an_order_waits_for_each_ack(sheet, a, b):
    r, on = sheet
    on(a, b)
    assert state_render.clause("results") == "results: state unreported"
    assert _say(a, 1, tab="results", selected=ROWS[0]["title"]) == 200
    assert _say(b, 1, tab="sources", selected="") == 200
    assert state_render.clause("results", dev=a).endswith(f': selected="{ROWS[0]["title"]}"')
    assert state_render.clause("results", dev=b).endswith(": tab=sources")
    from nucleo.flash import widget_read
    both = widget_read.read(INST)
    assert f'selected="{ROWS[0]["title"]}"' in both and "tab=sources" in both, "a worker read only one screen"
    assert r.apply_action("detail", {"sheet": SHEET, "title": ROWS[1]["title"]})["ok"]
    for d in (a, b):
        assert "selected=?ordered" in state_render.clause("results", dev=d), f"detail read as confirmed on {d}"
    assert _say(a, 2, full=True, tab="results", selected=ROWS[1]["title"]) == 200
    assert state_render.read("results", dev=a)["surfaces"][0]["pending"] == []
    assert "selected=?ordered" in state_render.clause("results", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_sheet_says_its_tab_and_record_through_the_door(sheet, card_page):
    r, on = sheet
    a, b = PAIRS[0]
    on(a, b)
    data = _route_data(SHEET)
    assert data["_rev"] == state.stamp(INST) != state.stamp("results"), "the instance acks the base sheet's revision"
    mount(card_page, "results", data, a, instance=INST)
    sent = posts(card_page)
    assert len(sent) == 1 and sent[0]["full"] and sent[0]["instance"] == INST and sent[0]["ack"] == data["_rev"]
    assert sent[0]["patch"] == {"tab": "results", "selected": ""}, sent
    assert deliver("results", sent) == [200]
    assert state_render.clause("results", dev=a).endswith(": at rest"), "the list on its first tab is rest"

    click(card_page, ".hr-tab[data-tab='sources']")                                 # his click
    sent = posts(card_page)
    assert len(sent) == 1 and not sent[0]["full"] and sent[0]["patch"] == {"tab": "sources"}, sent
    deliver("results", sent)

    r.apply_action("detail", {"sheet": SHEET, "title": ROWS[1]["title"]})            # the voice: that record
    assert "=?ordered" in state_render.clause("results", dev=a)
    push(card_page, _route_data(SHEET))
    sent = posts(card_page)
    assert sent and sent[-1]["full"] and sent[-1]["patch"] == {"tab": "results", "selected": ROWS[1]["title"]}, sent
    deliver("results", sent)
    assert state_render.clause("results", dev=a).endswith(f': selected="{ROWS[1]["title"]}"'), \
        state_render.clause("results", dev=a)
    after = state_render.clause("results", dev=a)                       # the dust settles (step-5 audit P1-1)
    settle(card_page, "results")
    assert state_render.clause("results", dev=a) == after, "a previous paint spoke after the last one"



def test_a_record_whose_row_is_gone_is_reported_as_the_list_it_paints(sheet, card_page):
    """Step-3 audit P2-2: the sheet on the detail of X, a new `present` replaces the rows and X is gone — the store still
    holds `view=detail, focus=X`, the card paints the LIST, and the report said `selected="X"` (the order, A7). It
    reports the record it painted."""
    r, on = sheet
    a, b = PAIRS[0]
    on(a, b)
    r.apply_action("detail", {"sheet": SHEET, "title": ROWS[1]["title"]})
    data = _route_data(SHEET)
    data["items"] = [{"title": "Taberna Nueva", "price": "20 €"}]          # the rows replaced under the open record
    assert data.get("view") == "detail" and data.get("focus") == ROWS[1]["title"]
    mount(card_page, "results", data, a, instance=INST)
    sent = posts(card_page)
    assert sent and sent[-1]["patch"] == {"tab": "results", "selected": ""}, f"the order was reported as painted: {sent}"


def test_the_digest_names_each_sheet_by_the_id_its_state_line_says(sheet):
    """Step-3 audit P2-3: with two sheets the state line says `results::s1@computer: tab=sources` and the digest headed
    each block `── HOJA «title» ──` — the brain could not join them. The block header carries the same id."""
    r, on = sheet
    on(*PAIRS[0])
    assert r.apply_action("present", {"sheet": "s2", "items": [{"title": "Otra mesa", "price": "9 €"}]})["ok"]
    from widgets.results import find
    text = find.prompt_digest()
    _say(PAIRS[0][0], 1, tab="sources", selected="")
    assert f"({INST}) ──" in text and "(results::s2) ──" in text, text[:300]
    assert state_render.clause("results", dev=PAIRS[0][0]).startswith(f"{INST}@")


def test_a_record_after_a_record_is_pending_on_its_second_key(sheet):
    """Step-3 audit P3: `selected` follows `view` AND `focus`; detail A → detail B moves only `focus`, and a first-key
    disarm left this green. B is `?ordered` until the screen acks it."""
    r, on = sheet
    a, b = PAIRS[0]
    on(a, b)
    r.apply_action("detail", {"sheet": SHEET, "title": ROWS[0]["title"]})
    assert _say(a, 1, tab="results", selected=ROWS[0]["title"]) == 200
    assert state_render.read("results", dev=a)["surfaces"][0]["pending"] == []
    r.apply_action("detail", {"sheet": SHEET, "title": ROWS[1]["title"]})              # only the focus moves
    assert "selected=?ordered" in state_render.clause("results", dev=a), state_render.clause("results", dev=a)

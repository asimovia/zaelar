"""The document card says which document each screen shows and the passage he is reading (V2-884 C8 step 5).

The sheet scrolls under his hand: «what does this part say?» means the passage on HIS screen, which the store cannot
know — it holds only the last `goto` (and a `goto` whose text the page does not carry marks nothing). The card says
`title` ("" = blank) and `at` (the marked passage after a `goto`, else the last heading above the top when he scrolls)
after every paint and on his scroll; a `show` or a `goto` is `?ordered` on each screen until it acks. Two screen
pairs; the rendered card through the real reporter into the real door. Disarms (named in the test): the card that
never reports → `state unreported`; no report on his scroll → the line keeps the passage he left; `at` following only
the document → a `goto` reads as confirmed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push, settle  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
HEADS = ["Ingredientes", "Masa madre", "Amasado", "Horneado", "Reposo", "Emplatado"]
BODY = "\n\n".join(["# Receta de prueba"] + [f"## {h}\n\n" + ("Texto de esta parte. " * 40) for h in HEADS])


@pytest.fixture
def doc(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.documento import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    assert data.apply_action("show", {"title": "Receta de prueba", "body": BODY}).get("ok") is not False

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["documento"]}, b: {"open": ["documento"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("documento", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                      "ack": state.stamp("documento")})[0]


def test_the_document_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/documento/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_passage_and_a_goto_waits_for_each_ack(doc, a, b):
    data, on = doc
    on(a, b)
    assert state_render.clause("documento") == "documento: state unreported"
    assert _say(a, 1, title="Receta de prueba", at="Masa madre") == 200 and _say(b, 1, title="Receta de prueba", at="") == 200
    assert state_render.clause("documento", dev=a).endswith(': title="Receta de prueba", at="Masa madre"')
    assert state_render.clause("documento", dev=b).endswith(': title="Receta de prueba"')
    assert data.apply_action("goto", {"text": "Reposo"}).get("ok") is not False
    for d in (a, b):
        assert "at=?ordered" in state_render.clause("documento", dev=d) and "title=?ordered" not in \
            state_render.clause("documento", dev=d), f"goto read wrong on {d}"
    assert _say(a, 2, full=True, title="Receta de prueba", at="Reposo") == 200
    assert "?ordered" not in state_render.clause("documento", dev=a)
    assert "at=?ordered" in state_render.clause("documento", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_sheet_says_the_passage_marked_and_the_one_he_scrolls_to(doc, card_page):
    data, on = doc
    a, b = PAIRS[0]
    on(a, b)
    data.apply_action("goto", {"text": "Masa madre"})
    mount(card_page, "documento", {**data.view_data(), "_rev": state.stamp("documento")}, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"title": "Receta de prueba", "at": "Masa madre"}, sent
    deliver("documento", sent)
    card_page.evaluate("""() => { const s = document.querySelector('.hbd-scroll');
        const h = [...s.querySelectorAll('h2')].find(x => x.textContent.includes('Amasado'));
        s.scrollTop = h.offsetTop + 2; }""")                                          # his hand on the page
    card_page.wait_for_timeout(600)
    sent = posts(card_page)
    deliver("documento", sent)
    assert state_render.clause("documento", dev=a).endswith(': title="Receta de prueba", at="Amasado"'), \
        f"his scroll was not said: {sent}"


def test_a_new_document_right_after_a_scroll_reads_the_new_one_after_the_dust_settles(doc, card_page):
    """Step-5 audit P2-1: a scroll armed a 300 ms report closed over the OLD document; a `show` within that window was
    then overwritten by the old title, acked at the new revision. The paint clears it, and a report said for data the
    screen no longer shows is dropped."""
    data, on = doc
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "documento", {**data.view_data(), "_rev": state.stamp("documento")}, a)
    settle(card_page, "documento")
    card_page.evaluate("() => { const s = document.querySelector('.hbd-scroll'); s.scrollTop = 400; }")   # his hand
    card_page.wait_for_timeout(50)
    data.apply_action("show", {"title": "Informe Beta", "body": "# Informe Beta\n\nTexto."})
    push(card_page, {**data.view_data(), "_rev": state.stamp("documento")})
    settle(card_page, "documento")
    line = state_render.clause("documento", dev=a)
    assert ': title="Informe Beta"' in line and "Receta" not in line, line

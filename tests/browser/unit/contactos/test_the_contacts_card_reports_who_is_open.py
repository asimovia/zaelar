"""The contacts card says WHOSE card is open on each screen — never the last order (V2-884 step 3, contactos).

A shared app: the computer can hold one person's card open while the phone reads the list. The brain could only read
the last push (`view.sel`) and speak it as what was on screen. Now the card says `selected` (the name it shows, "" =
none) after every paint, with the revision it applied; an order that moves the view (`show_contact`, a filter) leaves
it `?ordered` on every screen until each acks it. The rendered card (the real `widget.js`, the real reporter) feeds the
real door. Invented people. Disarms (named in the test): the card that never reports → `state unreported`; a field
that follows no order → an order reads as confirmed.
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
LUCIA, TOMAS = "Lucía Prados", "Tomás Ibarra"


@pytest.fixture
def ct(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.contactos import data as d
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — the move listener
    for name in (LUCIA, TOMAS):
        assert d.apply_action("add_contact", {"name": name}).get("ok") is not False

    def on(a, b):
        for dev in (a, b):
            screens.attach(dev)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["contactos"]}, b: {"open": ["contactos"]}})
    yield d, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _id(d, name):
    return next(c["id"] for c in d.load_db()["contacts"] if c["name"] == name)


def _say(dev, n, full=False, **fields):
    return state.report("contactos", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                      "ack": state.stamp("contactos")})[0]


def test_contactos_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/contactos/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None
    assert "adopt" not in json.dumps(man["state"]), "a shared app never adopts (C10 A3)"


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_says_whose_card_is_open(ct, a, b):
    d, on = ct
    on(a, b)
    assert state_render.clause("contactos") == "contactos: state unreported"
    assert _say(a, 1, selected=LUCIA) == 200 and _say(b, 1, selected="") == 200
    assert state_render.clause("contactos", dev=a).endswith(f': selected="{LUCIA}"')
    assert state_render.clause("contactos", dev=b).endswith(": at rest"), "no card open must read as rest"
    from nucleo.flash import widget_read
    assert f'selected="{LUCIA}"' in widget_read.read("contactos")
    assert d.apply_action("show_contact", {"contactId": _id(d, TOMAS)}).get("ok") is True
    for dev in (a, b):
        assert "selected=?ordered" in state_render.clause("contactos", dev=dev), \
            f"show_contact read as confirmed on {dev}"
    assert _say(a, 2, full=True, selected=TOMAS) == 200
    assert state_render.clause("contactos", dev=a).endswith(f': selected="{TOMAS}"')
    assert "selected=?ordered" in state_render.clause("contactos", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_card_says_who_is_open_through_the_door(ct, card_page):
    d, on = ct
    a, b = PAIRS[0]
    on(a, b)
    data = {**d.view_data(), "_rev": state.stamp("contactos")}
    mount(card_page, "contactos", data, a)
    sent = posts(card_page)
    assert len(sent) == 1 and sent[0]["full"] and sent[0]["ack"] == data["_rev"] and sent[0]["patch"] == {"selected": ""}
    deliver("contactos", sent)
    assert state_render.clause("contactos", dev=a).endswith(": at rest")

    card_page.evaluate("(n) => [...document.querySelectorAll('.ctrow')].find(r => r.textContent.includes(n)).click()",
                       LUCIA)
    card_page.wait_for_timeout(200)
    sent = posts(card_page)
    assert len(sent) == 1 and not sent[0]["full"] and sent[0]["patch"] == {"selected": LUCIA}, sent
    deliver("contactos", sent)

    d.apply_action("show_contact", {"contactId": _id(d, TOMAS)})                       # the voice
    pushed = {**d.view_data(), "_rev": state.stamp("contactos")}
    push(card_page, pushed)
    sent = posts(card_page)
    assert sent and sent[-1]["full"] and sent[-1]["ack"] == pushed["_rev"] and sent[-1]["patch"] == {"selected": TOMAS}
    deliver("contactos", sent)
    assert state_render.clause("contactos", dev=a).endswith(f': selected="{TOMAS}"')
    after = state_render.clause("contactos", dev=a)                       # the dust settles (step-5 audit P1-1)
    settle(card_page, "contactos")
    assert state_render.clause("contactos", dev=a) == after, "a previous paint spoke after the last one"

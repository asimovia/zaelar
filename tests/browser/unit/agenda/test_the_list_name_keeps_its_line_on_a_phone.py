"""RENDERED on a phone: the list's NAME is what reads as its name, never its identifier.

Measured on a phone (2026-11-16): the head of a list he made carries its number, its name, its identifier and three
actions on ONE line. At 360-390 px the name — the only member allowed to shrink — collapsed to nothing, and
`tl_shopping` stood where the name should be. On a narrow screen the name now keeps the first line to itself and the
identifier and the actions take the line below; a wide card is unchanged.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.browser.unit.agenda.test_the_tasks_half_is_two_delimited_panes import _box, _data, _mount, _page  # noqa: F401

STYLE = pathlib.Path(__file__).resolve().parents[4] / "widgets/agenda/js/style_panels.js"


def _phone(page, name="Groceries for the weekend"):
    page.set_viewport_size({"width": 375, "height": 760})
    d = _data()
    d["tasks"]["lists"][1]["name"] = name
    _mount(page, d, card_w=375, card_h=700)
    page.click('.agt-list[data-list="tl_2"]')
    page.wait_for_timeout(120)


@pytest.mark.parametrize("name", ["Groceries for the weekend", "Compra"])
def test_on_a_phone_the_name_is_whole_and_the_identifier_sits_under_it(_page, name):
    _phone(_page, name)
    title, ident, acts = _box(_page, ".agt-head .agt-title"), _box(_page, ".agt-head .agt-id"), _box(_page, ".agt-acts")
    assert title and ident and acts
    cut = _page.evaluate("() => { const t = document.querySelector('.agt-head .agt-title');"
                         " return t.scrollWidth > t.clientWidth + 1; }")
    assert title["w"] > 150 and not cut, f"the name is squeezed out of its own header: {title}"
    assert ident["y"] >= title["b"] - 1, "the identifier still shares the name's line"
    assert acts["rt"] <= 375 + 1 and ident["x"] >= 0, "the second line runs off the screen"
    assert _page.inner_text(".agt-head .agt-title") == name


def test_a_wide_card_keeps_its_one_line(_page):
    _page.set_viewport_size({"width": 1160, "height": 760})
    _mount(_page, _data())
    _page.click('.agt-list[data-list="tl_2"]')
    _page.wait_for_timeout(120)
    title, ident = _box(_page, ".agt-head .agt-title"), _box(_page, ".agt-head .agt-id")
    assert abs((title["y"] + title["h"] / 2) - (ident["y"] + ident["h"] / 2)) < 12, "the wide header was reflowed"


def test_disarmed_the_identifier_takes_the_names_place(_page):
    original = STYLE.read_text(encoding="utf-8")
    rule = re.search(r"    \.hb-agenda \.agt-head\{flex-wrap:wrap;[^\n]*\n    \.hb-agenda \.agt-head \.agt-title[^\n]*\n",
                     original)
    assert rule, "the narrow-screen rule is not where this disarm expects it"
    fresh = _page.context.browser.new_page()         # its own module cache: the page above already holds the style
    for k in ("_hb_url", "_hb_origin", "_hb_port"):
        setattr(fresh, k, getattr(_page, k))
    try:
        STYLE.write_text(original.replace(rule.group(0), ""), encoding="utf-8")
        _phone(fresh)
        title = _box(fresh, ".agt-head .agt-title")
        assert title["w"] < 60, f"the mutation did not land: the name still has room ({title})"
    finally:
        STYLE.write_text(original, encoding="utf-8")
        fresh.close()
    _phone(_page)
    assert _box(_page, ".agt-head .agt-title")["w"] > 150

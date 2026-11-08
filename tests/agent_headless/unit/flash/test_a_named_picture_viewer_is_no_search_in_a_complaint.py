"""A card NAME in a complaint is no picture search (measured live, 2026-11-08).

He pasted his own screenshot and said «as you can see in the image, nothing is playing»: «image» named the picture
viewer's alias and `picture_named_by` searched the web with his whole sentence. A name match alone never makes his
sentence a query: the brief must read the turn as an order or a question (or a canvas `show`), and a sure
`canvas = neither` refuses.
"""
from __future__ import annotations

import pytest

from nucleo.flash import card_commission as cc

COMPLAINTS = [
    "as you can see in the image, nothing is playing",
    "como ves en la imagen, no se está reproduciendo nada",
]
ORDERS = [
    "show me images of a red ferrari f40",
    "enséñame imágenes de un ferrari rojo f40",
]


@pytest.fixture
def brief(monkeypatch):
    from nucleo.turn import brief as _tb
    state: dict = {}

    def read(_brief, key, fallback, *, min_confidence=None):
        if key not in state:
            return fallback, None
        choice, conf = state[key]
        floor = 0.5 if min_confidence is None else min_confidence
        return (choice, {"confidence": conf, "used": True}) if conf >= floor else (fallback, None)
    monkeypatch.setattr(_tb, "read", read)
    monkeypatch.setattr(cc._fill, "is_empty", lambda card: True)
    return state


@pytest.mark.parametrize("said", COMPLAINTS)
def test_a_complaint_naming_the_image_searches_nothing(brief, said):
    from nucleo.turn import brief as _tb
    brief[_tb.REQUEST_KEY] = ("complaint", 0.9)
    assert cc.picture_named_by(said, object()) is None


@pytest.mark.parametrize("said", COMPLAINTS + ORDERS)
def test_a_sure_no_canvas_verdict_refuses_the_name(brief, said):
    from nucleo.turn import brief as _tb
    brief[_tb.REQUEST_KEY] = ("order", 0.9)
    brief[_tb.CANVAS_KEY] = ("neither", 0.95)
    assert cc.picture_named_by(said, object()) is None


@pytest.mark.parametrize("said", COMPLAINTS)
def test_a_brief_that_has_not_landed_is_no_licence_for_the_name(brief, said):
    assert cc.picture_named_by(said, object()) is None


@pytest.mark.parametrize("said", ORDERS)
def test_an_order_naming_the_empty_viewer_is_still_the_search(brief, said):
    from nucleo.turn import brief as _tb
    brief[_tb.REQUEST_KEY] = ("order", 0.9)
    got = cc.picture_named_by(said, object())
    assert got and got["query"] == said, got

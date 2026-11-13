"""«Close the widget video» is a CANVAS close, even though the video card declares an in-card action named `close`
(node 2.911).

Live, 2026-10-28 15:52 (T40–T48 of the operator's session): `screen_action = youtube:close` at 1.00 and `canvas = close`
at 0.87. `order_is_inside` read the action's name as «inside the card», the canvas close was ignored, the player was
unloaded instead, and the card stayed on screen through four more turns («I still see the YouTube widget»). An in-card
action that borrows the canvas verb's own name cannot, by itself, put the order inside the card: the canvas reader
leaning to close outvotes the alias. «Quita el vídeo» (canvas = neither) stays inside, and V2-770's agenda case is kept.

Disarm: with `_canvas_leans_close` answering False, the first test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import direct_action as card_verdict
from nucleo.turn import brief as _tb


def _brief(answers: dict, *, open_ids=("youtube",)):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


@pytest.fixture
def on_screen(monkeypatch):
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)


def test_close_the_widget_with_the_canvas_leaning_to_close_is_NOT_inside(on_screen):
    b = _brief({_tb.TARGET_KEY: ("youtube:close", 1.0), _tb.CANVAS_KEY: ("close", 0.87)})
    assert card_verdict.order_is_inside(b, "youtube") is False


def test_unload_the_video_with_no_canvas_close_stays_inside(on_screen):
    b = _brief({_tb.TARGET_KEY: ("youtube:close", 0.95), _tb.CANVAS_KEY: ("neither", 0.9)})
    assert card_verdict.order_is_inside(b, "youtube") is True


def test_an_action_that_merely_contains_close_is_still_inside(on_screen):
    """V2-770: «ya la puedes cerrar» over a detail card → `agenda:close_meeting`; the canvas may lean to close."""
    b = _brief({_tb.TARGET_KEY: ("agenda:close_meeting", 0.99), _tb.CANVAS_KEY: ("close", 0.6)}, open_ids=("agenda",))
    assert card_verdict.order_is_inside(b, "agenda") is True



@pytest.mark.parametrize("act", ["musica:release", "youtube:pause"])
def test_a_close_of_the_whole_screen_is_never_an_act_inside_a_card(on_screen, act):
    """V2-903 a4 (phone, 14:38): «…cierra todo y libera la pantalla» — canvas = close, `musica:release` at 0.80 — the model's
    TOTAL close (no card id) was dropped for the in-card act, which ran and said «Hecho.». A close of the whole screen
    names no card: no in-card act is its order while the canvas reader leans to close."""
    b = _brief({_tb.TARGET_KEY: (act, 0.80), _tb.CANVAS_KEY: ("close", 0.7), "names_a_card": ("nothing", 0.9)},
               open_ids=("musica", "youtube"))
    assert card_verdict.order_is_inside(b, "") is False


@pytest.mark.parametrize("names", ["on_screen", None])
def test_a_bare_close_tag_over_one_thing_keeps_the_act_inside(on_screen, names):
    """Audit P2-3: «ya la puedes cerrar» over a detail — `agenda:close_meeting` 0.99, canvas close 0.6 — with the model's
    bare [[close]] (no id) closed EVERY app. Only a sentence the brief reads as naming no app is a whole-screen close."""
    answers = {_tb.TARGET_KEY: ("agenda:close_meeting", 0.99), _tb.CANVAS_KEY: ("close", 0.6)}
    if names:
        answers["names_a_card"] = (names, 0.9)
    b = _brief(answers, open_ids=("agenda", "mensajeria"))
    assert card_verdict.order_is_inside(b, "") is True


def test_a_bare_close_with_no_canvas_close_can_still_be_inside(on_screen):
    """«ya la puedes cerrar» over a detail with the canvas reading neither: the in-card act keeps the order."""
    b = _brief({_tb.TARGET_KEY: ("agenda:close_meeting", 0.95), _tb.CANVAS_KEY: ("neither", 0.9)}, open_ids=("agenda",))
    assert card_verdict.order_is_inside(b, "") is True

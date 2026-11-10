"""The stream's last, EMPTY piece releases nothing a routed turn holds (node 2.1668, V2-874 class 6).

Measured with a probe on the sandbox (2026-11-10): on a routed turn (escalate 1.0 at the first word) the Hold appended
every piece to `route_pending`, and then the stream's closing `say(take(True))` — an empty piece when the model's last
chunk was already taken — skipped the hold (`if piece and …`) and fell into the block that flushes `route_pending`: all
the model's words went to the mouth, no 🤐, on 14/14 typed A1 turns and 6/6 S3 turns. The same pipeline speaks for
voice, so voice leaked too. Undecided or routed, the Hold now releases nothing on any piece; `release()` decides, bounded
by the route wait. The existing tests never sent the empty closing piece the real stream sends — these do.
Disarm: the hold applies only to a non-empty piece again → red.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.flash import follow_up_pass as FP
from nucleo.turn import brief as tb

WORDS = {"es": ("Voy a buscarlos", " y te los enseño", " en cuanto los tenga."),
         "en": ("Alright,", " give me a moment", " to look into that.")}


@pytest.fixture(params=["es", "en"])
def lang(request):
    return request.param


def _brief(choice, conf, ready=True):
    ev = threading.Event()
    if ready:
        ev.set()
    res = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": choice, "confidence": conf, "probs": {}}}
    return {"event": ev, "turn_id": "t", "result": res if ready else None}


def _stream(h, pieces):
    for p in pieces:
        h.say(p)
    h.say("")                       # what `pipeline_stream` sends last: `say(take(True))`, empty more often than not


def test_a_routed_turns_words_never_leave_on_the_closing_empty_piece(lang):
    sent, events = [], []
    h = FP.Hold(_brief("escalate", 1.0), sent.append, route_wait_s=1.5)
    _stream(h, WORDS[lang])
    assert sent == [], "the closing empty piece released the routed words"
    asyncio.run(h.release([], (), lambda *a, **k: events.append(a)))
    assert sent == [] and h.dropped == "".join(WORDS[lang])
    assert any("routed to its task" in e[1] for e in events)


def test_an_undecided_route_holds_through_the_closing_piece_until_release_decides(lang):
    sent = []
    late = _brief("escalate", 0.0, ready=False)
    h = FP.Hold(late, sent.append, route_wait_s=5.0)
    _stream(h, WORDS[lang])
    assert sent == [] and h.routed is None
    late["result"] = {"_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": 0.9, "probs": {}}}
    late["event"].set()
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert sent == [] and h.routed


def test_an_inline_turn_says_every_word_in_order(lang):
    sent = []
    h = FP.Hold(_brief("handle_inline", 0.9), sent.append, route_wait_s=1.5)
    _stream(h, WORDS[lang])
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert "".join(sent) == "".join(WORDS[lang]) and h.routed is False


def test_a_held_turn_that_reached_a_live_worker_is_never_mute(lang, monkeypatch):
    """Measured after the fix (sandbox es S3, 1 of 7): routed at 0.56, the words held, his correction went to the
    running errand as a steer — handled, nothing launched, so no start line: the turn said nothing at all."""
    from i18n import langs
    from nucleo.turn import wait_lines as W
    spec = langs.LANGUAGES[lang]
    assert W.owes_a_line("", handled=True, held_for_a_worker=True)
    assert not W.owes_a_line("", handled=True, held_for_a_worker=False), "a routed launch says its start line later"
    assert not W.owes_a_line("Sigo con ello.", handled=True, held_for_a_worker=True)
    assert W.owes_a_line("", handled=False, held_for_a_worker=False)
    from nucleo.workers import quota_wait
    monkeypatch.setattr(quota_wait, "asleep_line", lambda window, lg: "")   # the worker chain is awake
    assert W.mute_backstop([], spec, True) == spec.filler_still_working
    unrelated = "abre el que sea mejor oferta" if lang == "es" else "open the one that's the best deal"
    assert W.mute_backstop([], spec, False, unrelated, reached_worker=True) == spec.filler_still_working, \
        "a turn that reached the worker is about its work, whatever his words share with its title"

"""A claimed act nobody ran is said undone (CRIT-V12, `nucleo/turn/unserved`).

Measured in the use-case battery of 2026-11-06, ES and US, agenda and screen: «Cambio el aviso a las doce…» over an
`agenda:set_reminder` call the engine diverted and never ran; «I've cancelled just next Tuesday's piano» and «I've
cleared it» with ZERO calls. The mouth composes the turn's line from the acts that RAN, so an act that reached no door
had no verdict and the narration stood. Now the verdict is `unmet`, always said after the model's words: a model call
on a card no door of the turn touched, a sure order aimed at a card or the canvas that no door served, or a sure order
naming ONE card that the model served with a call on another (V2-909 F1: «write to <name> on whatsapp» → `show_panel`
and «Done.»).

Disarm: make `unserved.outcomes` return [] (or `calls_not_run` return []) and the first two tests go red;
`served_elsewhere` answering False turns the served-on-another-card case red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus
from nucleo.circuit import verdict as V
from nucleo.turn import brief as tb, reply, unserved, verdicts

SP = type("S", (), {"sanitize": staticmethod(lambda t, **_: t)})


class _Done:
    def __init__(self, res):
        self._r = res

    def done(self):
        return True

    def cancelled(self):
        return False

    def result(self):
        return self._r


OK = {"ok": True, "result": {"title": "x"}}


@pytest.fixture
def turn(monkeypatch):
    """The brief as a dict of verdicts; no card acts; every manifest action reads as an act (never a read)."""
    v: dict = {}

    def read(h, key, fb, min_confidence=None):
        floor = verdicts.LICENCE if min_confidence is None else min_confidence
        t = v.get(key)
        return t if t and t[1]["confidence"] >= floor else (fb, None)
    monkeypatch.setattr(verdicts, "read", read)
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [])
    monkeypatch.setattr("nucleo.turn.brief_turn.of_this_turn", lambda: {})
    monkeypatch.setattr("widgets.effects.carries", lambda card, action, effect: False)
    reply._NOTED.clear()
    reply._ASKED.clear()
    unserved._WAITING.clear()
    return v


def _say(said, *, calls=(), tasks=(), quiet=True, held=False):
    out: list[str] = []
    text = asyncio.run(reply.after_acts(list(tasks), said, out.append, SP, model_calls=list(calls), quiet=quiet,
                                        held=held))
    return text, [o.strip() for o in out]


def _call(card, action, **payload):
    return {"name": "widget_data", "args": {"widget_id": card, "action": action, "payload": payload}}


ORDER = {"request_type": ("order", {"confidence": 0.84}), "wants_words": ("act", {"confidence": 0.78})}


@pytest.mark.parametrize("lang, said, card", [
    ("es", "Cambio el aviso a las doce del mediodía del día 16.", "agenda"),
    ("en", "Moving the training one ahead of the insane one.", "youtube"),
])
def test_a_model_call_no_door_ran_is_said_undone_naming_the_card(turn, monkeypatch, lang, said, card):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    from nucleo.flash import card_receipt
    name = card_receipt.card_name(card)
    text, out = _say(said, calls=[_call(card, "set_reminder" if card == "agenda" else "move")], quiet=True)
    assert out == [langs.current_language().reply_not_run.format(cards=name)], out
    assert text.startswith(said) and name in text


@pytest.mark.parametrize("lang, said, lean", [
    ("en", "Nothing's on screen to exit from — but I've cleared it, so you're at an empty canvas now.",
     ("canvas", "exit_fullscreen", 1.0)),
    ("es", "Hecho, te he quitado la clase del martes que viene.", (tb.CATALOG_KEY, "agenda", 0.93)),
    ("en", "Sure — I've cancelled just next Tuesday's piano with Abril.", (tb.TARGET_KEY, "agenda:cancel_meeting", 0.6)),
])
def test_a_sure_order_about_a_card_with_no_call_and_nothing_run_is_said_undone(turn, monkeypatch, lang, said, lean):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    turn.update(ORDER)
    key, choice, conf = lean
    turn[key] = (choice, {"confidence": conf})
    text, out = _say(said, calls=[], quiet=True)
    assert out == [langs.current_language().reply_nothing_done], out
    assert text.startswith(said)


def test_a_card_that_acted_this_turn_owes_nothing_for_the_call(turn):
    """The verdict completed or replaced the call on that card (CRIT-K2): no «not done» beside a landed op."""
    _t, out = _say("Done.", calls=[_call("youtube", "move")], tasks=[("youtube::remove", _Done(OK))], quiet=False)
    assert not any("YouTube" in o for o in out), out
    assert unserved.calls_not_run([_call("agenda", "set_reminder")], [("agenda::add_meeting", _Done(OK))]) == []
    assert unserved.calls_not_run([_call("agenda", "set_reminder")], []) == [("agenda", "set_reminder")]


@pytest.mark.parametrize("said, calls, quiet, held, brief", [
    ("¿A qué hora lo pongo?", [_call("agenda", "set_reminder")], True, False, {}),          # the turn ends asking him
    ("Cambio el aviso.", [_call("agenda", "set_reminder")], True, True, {}),                  # an act held for his yes
    ("Anotado: nada con gluten para ti.", [], True, False,
     {"request_type": ("comment", {"confidence": 0.92}), "wants_words": ("act", {"confidence": 0.56}),
      tb.CATALOG_KEY: ("none", {"confidence": 0.92})}),                                      # a comment, not an order
    ("It's up on your screen now.", [], True, False,
     {"request_type": ("comment", {"confidence": 0.3}), "wants_words": ("tell", {"confidence": 0.6})}),
    ("Tuesday you have piano at three.", [], True, False,
     {**ORDER, "wants_words": ("tell", {"confidence": 0.9}), tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}),
    ("Remember it, no gluten.", [], True, False, dict(ORDER)),                               # an order aimed at no card
    ("Done.", [], False, False, {**ORDER, tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}), # a door of the turn ran
])
def test_nothing_is_said_undone_when_the_turn_asked_held_answered_or_acted(turn, said, calls, quiet, held, brief):
    turn.update(brief)
    _t, out = _say(said, calls=calls, quiet=quiet, held=held)
    assert out == [], out


MESSAGING = {**ORDER, tb.CATALOG_KEY: ("mensajeria", {"confidence": 0.9})}
SEND_AIM = {**ORDER, tb.TARGET_KEY: ("mensajeria:send_to", {"confidence": 0.9})}


@pytest.mark.parametrize("lang, said, calls, brief", [
    ("en", "Done.", [{"name": "recall", "args": {}}], {**ORDER, tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})}),
    ("en", "Done.", [{"name": "show_panel", "args": {"panel": "connectors"}}], MESSAGING),
    ("es", "Hecho.", [{"name": "show_panel", "args": {"panel": "connectors"}}], SEND_AIM),
    ("es", "Listo, te lo enseño.", [{"name": "play_video", "args": {"query": "x"}}], MESSAGING),
])
def test_a_sure_order_served_on_another_card_is_said_undone(turn, monkeypatch, lang, said, calls, brief):
    """Reader 3: the model called something, but nothing addressing the ONE card the order names, no data-op ran and
    no door touched that card — `unmet`, said after the model's words."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    turn.update(brief)
    text, out = _say(said, calls=calls, quiet=False)
    assert out == [langs.current_language().reply_nothing_done], out
    assert text.startswith(said)


@pytest.mark.parametrize("said, calls, tasks, brief", [
    ("Done.", [{"name": "show_panel", "args": {"panel": "mensajeria"}}], (), MESSAGING),       # a call names the card
    ("Done.", [{"name": "play_video", "args": {"query": "x"}}], (),
     {**ORDER, tb.CATALOG_KEY: ("youtube", {"confidence": 0.9})}),                            # the tool drives the card
    ("Done.", [{"name": "show_panel", "args": {"panel": "connectors"}}], [("agenda::add_meeting", _Done(OK))],
     MESSAGING),                                                                              # a data-op ran elsewhere
    ("¿A quién se lo mando?", [{"name": "show_panel", "args": {"panel": "connectors"}}], (), MESSAGING),  # it asked
    ("Done.", [{"name": "show_panel", "args": {"panel": "connectors"}}], (),
     {**MESSAGING, "wants_words": ("tell", {"confidence": 0.9})}),                           # he wanted words
    ("Done.", [{"name": "show_panel", "args": {"panel": "connectors"}}], (), dict(ORDER)),   # an order naming no card
])
def test_a_sure_order_served_on_another_card_says_nothing_when_the_card_was_addressed_or_the_turn_wrote_or_asked(
        turn, said, calls, tasks, brief):
    turn.update(brief)
    _t, out = _say(said, calls=calls, tasks=tasks, quiet=False)
    assert out == [], out


def test_a_door_that_touched_the_ordered_card_owes_nothing(turn, monkeypatch):
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [("mensajeria", "card", "show")])
    turn.update(MESSAGING)
    _t, out = _say("Done.", calls=[{"name": "show_panel", "args": {"panel": "connectors"}}], quiet=False)
    assert out == [], out


def test_the_ordered_card_is_the_catalogue_choice_else_the_screen_actions_card(turn):
    turn.update(SEND_AIM)
    assert unserved.ordered_card({}) == "mensajeria"
    turn.update(MESSAGING)
    turn[tb.TARGET_KEY] = ("agenda:add_meeting", {"confidence": 0.9})
    assert unserved.ordered_card({}) == "mensajeria"
    turn.clear()
    turn.update({**ORDER, tb.CATALOG_KEY: ("none", {"confidence": 0.9})})
    assert unserved.ordered_card({}) == ""


def test_disarmed_reader_three_turns_the_served_elsewhere_case_red(turn, monkeypatch):
    """Disarm: `served_elsewhere` answers False (the reader unwired) → the order served on another card says nothing."""
    monkeypatch.setattr(unserved, "served_elsewhere", lambda brief, tasks, model_calls: False)
    with pytest.raises(AssertionError):
        test_a_sure_order_served_on_another_card_is_said_undone(
            turn, monkeypatch, "en", "Done.", [{"name": "show_panel", "args": {"panel": "connectors"}}], MESSAGING)


@pytest.mark.parametrize("said, asking", [("", False), ("   ", False), ("¿Se lo mando?", True), ("Which one?»", True),
                                           ("Done.", False)])
def test_an_empty_reply_never_reads_as_ending_asking(said, asking):
    assert unserved._ended_asking(said) is asking


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_silent_turn_that_served_the_order_on_another_card_is_said_undone(turn, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    turn.update(MESSAGING)
    _t, out = _say("", calls=[{"name": "show_panel", "args": {"panel": "connectors"}}], quiet=False)
    assert out == [langs.current_language().reply_nothing_done], out


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_silent_turn_whose_card_call_nobody_ran_is_said_not_run(turn, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    from nucleo.flash import card_receipt
    _t, out = _say("", calls=[_call("agenda", "set_reminder")], quiet=True)
    assert out == [langs.current_language().reply_not_run.format(cards=card_receipt.card_name("agenda"))], out


def test_disarmed_an_empty_reply_read_as_asking_silences_the_silent_turn(turn, monkeypatch):
    """Disarm: `_ended_asking` back to `last in marks` (the empty string is in every string) → the silent turn is red."""
    monkeypatch.setattr(unserved, "_ended_asking",
                        lambda said: str(said or "").rstrip().rstrip("»\"'”)")[-1:] in unserved._QUESTION_MARKS)
    with pytest.raises(AssertionError):
        test_a_silent_turn_that_served_the_order_on_another_card_is_said_undone(turn, monkeypatch, "en")
    with pytest.raises(AssertionError):
        test_a_silent_turn_whose_card_call_nobody_ran_is_said_not_run(turn, monkeypatch, "en")


def test_a_read_that_did_not_run_is_no_act_to_say_undone(turn, monkeypatch):
    monkeypatch.setattr("widgets.effects.carries", lambda card, action, effect: True)
    assert unserved.calls_not_run([_call("agenda", "list_day")], []) == []


def test_the_turn_hands_the_mouth_the_models_calls_and_whether_any_door_ran():
    """The wiring: the one call of `after_acts` in the post-stream settle passes the model's calls, `quiet` and `held`
    (a mouth that never receives them says nothing undone, and every test above would still be green)."""
    import ast
    import inspect
    from nucleo.flash import post_stream_settle
    tree = ast.parse(inspect.getsource(post_stream_settle))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "after_acts"]
    assert len(calls) == 1, "the turn's acts are said through ONE call of after_acts"
    kw = {k.arg: ast.unparse(k.value) for k in calls[0].keywords}
    assert {"model_calls", "quiet", "held"} <= set(kw), kw
    assert "_turn_calls" in kw["model_calls"], kw["model_calls"]


def test_a_turn_whose_words_wait_behind_an_act_is_not_a_silent_one(turn):
    """The hold deferred the model's words to the turn's end: nothing is said undone over an answer still to come."""
    turn.update({**ORDER, tb.CATALOG_KEY: ("agenda", {"confidence": 0.9})})
    unserved.waiting()
    _t, out = _say("", calls=[], quiet=True)
    assert out == [], out
    unserved._WAITING.clear()
    _t, out = _say("", calls=[], quiet=True)
    assert out, "with no words waiting the silent turn is said undone"

"""The worker's brief hands over his literal words and the act the turn identified, as its first step.

Measured: a «create a group» errand reached its worker as a paraphrase with no card and no action; the worker ran
~20 chained searches for more than 15 minutes and never created the group. The turn's `screen_action` verdict had
named the card's action, and the reading travelled on the row — only the exit door read it. Now the brief carries
his sentence verbatim and, when the verdict is sure and the card declares the action, the action's declared fields
and the one call that runs it (generalising the send row's block). Variants: two cards, two languages.
"""
from __future__ import annotations

import pytest

from nucleo.workers.prompts import first_act


def _reading(choice: str, confidence: float) -> dict:
    return {"result": {"screen_action": {"choice": choice, "confidence": confidence}}, "open_ids": [], "turn_id": "t1",
            "judged": "x"}


@pytest.fixture(params=["es", "en"])
def lang(request, monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: request.param)
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[request.param])
    return request.param


@pytest.mark.parametrize("choice,fields", [("contactos:create_group", ("name", "contactIds")),
                                           ("contactos:rename_group", ("groupId", "name"))])
def test_a_sure_identified_act_is_the_first_step_with_its_declared_fields(lang, choice, fields):
    said = {"es": "crea un grupo con Ana y Luis que se llame cena", "en": "make a group called dinner with Ana and Luis"}
    out = first_act.block("", {"said": said[lang]}, _reading(choice, 0.95))
    assert f"«{said[lang]}»" in out, "his words ride verbatim"
    wid, act = choice.split(":")
    import shlex
    cmd = shlex.split(out.split("`python -m nucleo.cli.widget data ")[1].split("`")[0])
    assert cmd == [wid, act, *(f"{f}=<…>" for f in fields)], "ONE command, every declared field an argument"
    for f in fields:
        assert f"· {f}:" in out


def test_a_doubtful_verdict_or_an_undeclared_action_hands_over_no_act(lang, monkeypatch):
    from nucleo.workers import state_now
    monkeypatch.setattr(state_now, "block", lambda own="": "")
    assert first_act.act_block(_reading("contactos:create_group", 0.2)) == ""
    assert first_act.act_block(_reading("contactos:no_such_action", 0.99)) == ""
    assert first_act.act_block({}) == ""
    assert first_act.block("", {}, {}) == "", "nothing to hand over is no block at all"


def test_disarmed_a_reading_that_is_not_read_hands_over_nothing(lang, monkeypatch):
    """RED proof: with the reading unread (the pre-handoff wiring), the act never reaches the brief."""
    monkeypatch.setattr(first_act, "identified", lambda reading: ("", "", {}))
    assert "create_group" not in first_act.block("", {"said": "x"}, _reading("contactos:create_group", 0.95))


def test_the_dispatch_hands_the_row_reading_and_context_to_the_brief():
    """The one door a worker starts through composes the handoff from the row (not a second reader elsewhere)."""
    import inspect

    from nucleo.dispatch import session
    src = inspect.getsource(session._run_session)
    assert "first_act.block(" in src and "rec.reading" in src and "task.context" in src

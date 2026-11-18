"""A bare «Done.» stands only when the cards back it (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: the recipe was owed on the document sheet — an end state re-read every five seconds as
UNMET — and the turn that resolved the build question with a «no» said the canned «Done.» over the empty sheet. The
bare acknowledgement WE are about to say is checked against the end states owed on the cards the turn wrote to, and
against the errands the turn just started (`nucleo/turn/reply_receipts.bare_ack`, refactor2710-03): our own line is
chosen from the facts, never repaired by reading words afterwards.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo.circuit import spec
from voice import trace
from nucleo.turn import reply_receipts
from widgets.documento import data as documento

BODY = {"widget": "documento", "field": "body", "expect": "present"}


@pytest.fixture(autouse=True)
def _clean():
    spec.reset()
    documento.apply_action("clear", {})
    yield
    spec.reset()
    documento.apply_action("clear", {})


def _lang():
    return langs.current_language()


def test_done_over_an_empty_sheet_that_is_owed_is_not_said():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, None) == _lang().done_not_on_card


def test_done_over_a_sheet_that_holds_its_body_stands():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    documento.apply_action("show", {"kind": "markdown", "title": "Carbonara", "body": "# Carbonara\n\n- 400 g spaghetti"})
    assert reply_receipts.bare_ack(_lang().data_ack, None) == _lang().data_ack


def test_done_over_an_errand_this_turn_just_started_is_not_said():
    assert reply_receipts.bare_ack(_lang().data_ack, None, beside=True) == _lang().done_just_started


@pytest.mark.parametrize("said", ["ok book it, call it catch up with Rowan", "vale, resérvalo, llámalo ponerme al día con Rowan"])
def test_an_end_state_another_request_left_open_never_unsays_this_turns_ack(said):
    """Demo sandbox 2026-10-28, C2/C3: an INIT «remember» item had inferred three agenda tasks nobody asked for, the
    spec stayed open and unmet all session, and the slot found and the meeting booked were both acked with «It isn't
    on the card yet». Only the end states born in THIS turn are read — by the turn's identity (its trace), never by
    comparing his sentence with the spec's copy of it (V2-831 audit A5)."""
    earlier, now = trace.begin("Remember these future responsibilities", origin="turno"), None
    spec.open({"widget": "agenda", "collection": "tasks", "where": {"title~": "Tesla insurance renewal"}},
              text="Remember these future responsibilities even when they are not on the calendar", widget="agenda")
    now = trace.begin(said, origin="turno")
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}) == _lang().done_not_on_card, "without a turn: as before"
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}, turn=now) == _lang().data_ack
    # its own end state stays — even when the spec's copy of his words is not his sentence (cut at 300 chars, or the
    # judged words differ from the raw ones), which is where matching by text went silent
    spec.open(BODY, text=(said + " — " + "x" * 400)[:300], widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}, turn=now) == _lang().done_not_on_card, "its own stays"
    assert earlier != now


def test_the_same_sentence_said_again_is_another_turn():
    first = trace.begin("give me the carbonara recipe", origin="turno")
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    again = trace.begin("give me the carbonara recipe", origin="turno")
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}, turn=again) == _lang().data_ack, \
        "an older request's end state was read as this turn's because the words matched"
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}, turn=first) == _lang().done_not_on_card


def test_a_write_on_another_card_is_judged_by_that_card_only():
    spec.open(BODY, text="give me the carbonara recipe", widget="documento")
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}) == _lang().data_ack
    assert reply_receipts.bare_ack(_lang().data_ack, {"documento"}) == _lang().done_not_on_card


def test_done_over_an_act_that_declares_nothing_to_check_it_is_said_as_asked():
    """The engine's «Done.» is a completion only an attested act earns (2026-11-18): an act with no `done_when` and no
    `instant` (the debt of `test_every_action_says_how_its_done_is_checked`) is said as asked, never as done."""
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda"}, ops=[("agenda", "snooze")]) == _lang().done_asked
    assert reply_receipts.unattested([("agenda", "snooze"), ("agenda", "add_meeting")]) == [("agenda", "snooze")]


@pytest.mark.parametrize("ops", [[("contactos", "show_view")], [("agenda", "add_meeting")], None, []])
def test_done_over_an_attested_act_stands(ops):
    """`instant` (the op's answer IS its end state) or a `done_when` the circuit judges: the ack stands as before."""
    assert reply_receipts.bare_ack(_lang().data_ack, {"agenda", "contactos"}, ops=ops) == _lang().data_ack


def test_a_cards_receipt_is_never_replaced_by_the_asked_line():
    """The ack already became a card's receipt (it names what closed and what is left): its own line stays."""
    receipt = "I closed the agenda; the music is still open."
    assert reply_receipts.bare_ack(receipt, {"agenda"}, ops=[("agenda", "snooze")]) == receipt


def test_disarmed_every_act_read_as_declared_says_done_again(monkeypatch):
    """Disarm: `spec.declares_done` answers True for every act → «Done.» over the undeclared act → red."""
    monkeypatch.setattr(spec, "declares_done", lambda wid, action: True)
    assert spec.declares_done("agenda", "snooze"), "the disarm landed"
    with pytest.raises(AssertionError):
        test_done_over_an_act_that_declares_nothing_to_check_it_is_said_as_asked()


def test_the_turns_bare_ack_is_given_the_turns_ops():
    """The wiring: the one `bare_ack` call of the post-stream settle passes the turn's ops (without them every test
    above stays green and the voice still says «Done.» over an act nobody attests)."""
    import ast
    import inspect
    from nucleo.flash import post_stream_settle
    calls = [n for n in ast.walk(ast.parse(inspect.getsource(post_stream_settle))) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "bare_ack"]
    assert len(calls) == 1 and "ops" in {k.arg for k in calls[0].keywords}, [ast.unparse(c) for c in calls]

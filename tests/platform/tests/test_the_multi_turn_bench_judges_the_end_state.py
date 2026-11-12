"""The multi-turn kindergarten bench (`tests/platform/parvulario_turns.py`) judges where a conversation LEFT things.

The bench itself is live (it spends model calls); what is pinned here, deterministically, is its shape and its judge:
every class runs in Spanish AND English, every case has more than one turn or a seeded offer, every case states an end
state, and the judge reads that end state — the agenda rows and the message acts — not the wording of a reply.
"""
from __future__ import annotations

import datetime as dt

from tests.platform import parvulario_turns as pt

TODAY = dt.date(2026, 11, 12)          # a Thursday


def _row(title, date, start, end=""):
    return {"title": title, "date": date, "startTime": start, "endTime": end}


def test_every_class_runs_in_both_languages_and_states_an_end_state():
    by_class: dict[str, set] = {}
    for cid, lang, klass, seed, turns, end in pt.CASES:
        base = cid.rsplit("-", 1)[0]
        by_class.setdefault(base, set()).add(lang)
        assert len(turns) >= 2 or seed.get("history"), f"{cid}: a multi-turn case has turns before the last one"
        assert set(end) & {"has", "lacks", "sent"}, f"{cid}: no end state"
        assert set(end) <= {"has", "lacks", "after", "sent", "not_sent"}, cid
    assert all(langs == {"es", "en"} for langs in by_class.values()), by_class
    assert len({c[0] for c in pt.CASES}) == len(pt.CASES)


def test_the_judge_reads_the_rows_not_the_reply():
    has = [pt.meeting("lucio", day="+2", start="21:00")]
    lacks = [pt.meeting("lucio", day="+1")]
    moved = [_row("Cena en Casa Lucio", "2026-11-14", "21:00")]
    stayed = [_row("Cena en Casa Lucio", "2026-11-13", "21:00")]
    assert pt.agenda_failures(moved, has, lacks, TODAY) == []
    why = pt.agenda_failures(stayed, has, lacks, TODAY)
    assert len(why) == 2 and "lacks" in why[0] and "still holds" in why[1]
    both = moved + stayed                          # a correction that ADDED instead of moving is red too
    assert pt.agenda_failures(both, has, lacks, TODAY)


def test_the_hours_and_the_next_saturday_are_part_of_the_row():
    want = [pt.meeting("alfonso", day="sat", start="14:00", end="16:00")]
    assert pt.resolve_day("sat", TODAY) == "2026-11-14"
    assert pt.agenda_failures([_row("Comida en el Alfonso XIII", "2026-11-14", "14:00", "16:00")], want, (), TODAY) == []
    assert pt.agenda_failures([_row("Comida en el Alfonso XIII", "2026-11-14", "14:00", "15:00")], want, (), TODAY)
    assert pt.agenda_failures([_row("Comida en el Alfonso XIII", "2026-11-14", "9:00", "16:00")], want, (), TODAY)


def test_a_message_to_the_other_person_is_red_even_when_the_right_one_also_went():
    right = {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "send_to",
                                             "payload": {"name": "Raquel Jofre", "text": "llego tarde"}}}
    wrong = {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "send_to",
                                             "payload": {"contact": "Raquel Salvador Esteban", "text": "llego tarde"}}}
    reply = {"name": "reply_message", "args": {"n": 1, "text": "llego tarde"}}
    assert pt.message_failures([right], ["jofre", "tarde"], ["salvador"]) == []
    assert pt.message_failures([wrong, right], ["jofre", "tarde"], ["salvador"]) == ["a message act went to 'salvador'"]
    assert pt.message_failures([reply], ["jofre", "tarde"], ["salvador"]), "a reply to an inbox row is a send act"
    assert pt.message_failures([], ["jofre"], ())


def test_only_the_local_cards_door_opens_inside_the_dry_turn():
    from nucleo import consequence
    real = consequence.passes
    with consequence.dry_turn(ingest=False), pt._LocalCardsOpen():
        assert consequence.passes("widget.data", widget="agenda", action="add_meeting") is True
        assert consequence.passes("widget.data", widget="contactos", action="set_alias") is True
        assert consequence.passes("widget.data", widget="mensajeria", action="send_to") is False
        assert consequence.passes("worker.spawn") is False
        assert consequence.passes("cron.create") is False
    assert consequence.passes is real


def test_a_send_row_waiting_on_its_which_question_sent_nothing():
    """The judge reads the send ROWS when the turns opened any: the model's call to the wrong Raquel that the row turned
    into «which Raquel?» went nowhere; the row his answer filled is what went."""
    asked = {"widget": "mensajeria", "action": "send_to", "payload": {"contact": "Raquel Salvador Esteban",
                                                                       "text": "llego tarde"}, "went": False}
    filled = {"widget": "mensajeria", "action": "send_to", "payload": {"contact": "Raquel Jofre", "text": "llego tarde"},
              "went": True}
    wrong_call = {"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "send_to",
                                                  "payload": {"contact": "Raquel Salvador Esteban", "text": "llego tarde"}}}
    assert pt.message_failures([wrong_call], ["jofre", "tarde"], ["salvador"], rows=[asked, filled]) == []
    assert pt.message_failures([], ["jofre"], (), rows=[asked]), "a row still asking is no send"
    assert pt.two_raquels()["contacts"][2]["channels"][0]["last_seen"] > 0

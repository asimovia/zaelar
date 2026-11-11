"""The card his words name carries each act's declared slots, on its own line (V2-879).

The row said `· datos: set, start, pause, reset` — the act's name only — and the model filled `set` in its own
vocabulary (`minutes`, `duration`) on a card that reads `seconds`. The card this turn's words NAME now carries
`[timer] campos: set: seconds·label`, every offered act's keys from the one declaration (`_payload_keys`), on their own
line so no key is ever read as part of an act's name (V2-838). Only the named card: every card's keys on every turn
measured +917 tokens; this way an idle turn pays 0, the timer turn +12, the map turn +27. A card on screen keeps its
own line (the acts that declare a `how`), unchanged.
"""
from __future__ import annotations

import pytest

from widgets import brief


def _lines(text: str, wid: str, open_ids=()) -> list[str]:
    out = brief.for_prompt(list(open_ids), [], text).splitlines()
    return [ln for ln in out if ln.startswith(f"- {wid} ") or ln.startswith(f"  [{wid}] campos:")]


@pytest.mark.parametrize("said", ["pon un temporizador de 10 minutos", "set a 10-minute timer"])
def test_the_card_he_names_carries_each_acts_slots_on_its_own_line(said):
    row, fields = _lines(said, "timer")
    assert "set: seconds·label" in fields, fields
    assert "seconds" not in row, "a key read as part of an act's name"
    assert "start:" not in fields, "an act that declares no slot is listed with none"


def test_a_card_he_did_not_name_carries_names_only():
    assert len(_lines("pon un temporizador de 10 minutos", "map")) == 1


def test_an_idle_turn_pays_nothing():
    assert not [ln for ln in brief.for_prompt([], [], "hola").splitlines() if "] campos:" in ln]

"""The brief's screen question reads each open card's rows ONCE, however many actions the card declares (V2-935).

Measured on his engine (2026-11-18): with a directory of 2 700 people on screen, every end of turn held the event
loop for 6.4 s. The question «which declared action does he mean?» asked the card for its published rows once per
action that must name a row — 24 of the directory's 33 — and each ask re-read and digested the whole store (98 ms).
"""
from __future__ import annotations

import pytest

from nucleo.turn import brief_screen


@pytest.fixture
def card(monkeypatch):
    """A card with `n` actions that each must name an existing row (`contactId`), and an index that counts its reads."""
    from nucleo.flash import frontend
    from widgets import refs
    reads = {"n": 0, "rows": [{"field": "contactId", "id": "c1", "label": "Quinn Ferrer"}]}

    def _index(base):
        reads["n"] += 1
        return list(reads["rows"])
    acts = {f"act_{i}": {"desc": f"does thing {i} to one person"} for i in range(24)}
    monkeypatch.setattr(frontend, "declared_actions", lambda base: acts if base == "people" else {})
    monkeypatch.setattr(refs, "id_field_for_action", lambda base, action: "contactId")
    monkeypatch.setattr(refs, "selector_is_optional", lambda base, action, field: False)
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda base: True)
    monkeypatch.setattr(refs, "_ref_index", _index)
    monkeypatch.setattr(brief_screen, "_card_label", lambda wid: wid)
    return reads


def test_a_card_with_many_row_actions_is_read_once(card):
    q = brief_screen.target_question(["people"])
    assert len(q["criteria"]) == 25, "24 actions and «none»"
    assert card["n"] == 1, "one read of the card's rows for the whole question"


def test_two_open_cards_are_two_reads_and_an_empty_card_still_drops_its_row_actions(card):
    card["rows"] = []
    assert brief_screen.target_question(["people", "people::t2"]) is None, "no rows: no action that names one"
    assert card["n"] == 1, "two instances of one card share its rows"


def test_disarm_without_the_memo_every_action_reads_the_card(card):
    assert brief_screen._possible_now("people", "act_0") and brief_screen._possible_now("people", "act_1")
    assert card["n"] == 2, "this is the per-action read the question no longer makes"

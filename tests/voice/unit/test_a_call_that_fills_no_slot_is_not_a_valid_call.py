"""A model call that fills none of its act's slots is not the «valid call» that runs over the verdict (V2-754).

Demo pass on a sandbox, 2026-11-14 (step F2, «go to the part about proof of work», a document on screen). The brief
read `screen_action = documento:goto` at 0.99. The model called `documento:show {"goto": "<a section>"}`: the
action that REPLACES the document, carrying the name of the sibling action as its only key. Two mechanisms let it
through:

  · the text-field fold (`contract._fold_text_field`) took the one loose text key, `goto`, as `show`'s `body` —
    so a call naming another action of the same card read as a document to write, and the sheet was replaced;
  · the arbitration site runs a «valid» model call over a disagreeing verdict, and judged validity before the fold
    and without the act's slots.

The rule, read from what each manifest declares: a key that NAMES an action of the same card is that action's word,
never free text for another; and a call that, folded, fills none of its act's declared slots is not a valid call —
the verdict's action on that card completes the turn instead.

Run: .venv/bin/pytest tests/voice/unit/test_a_call_that_fills_no_slot_is_not_a_valid_call.py
"""
from __future__ import annotations

import pytest

from widgets import contract as C
from widgets import runtime as _rt

from tests.voice.unit.test_the_verdict_completes_the_model import _ran, _voice_turn


def _text_field_acts():
    """Every (card, action, sibling) where the action declares a text field and the card declares another action."""
    rows = []
    for wid in sorted(w["id"] for w in _rt.catalog()):
        acts = (_rt.get(wid) or {}).get("actions") or {}
        for name, spec in acts.items():
            if isinstance(spec, dict) and str(spec.get("text_field") or "").strip():
                declared = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
                rows += [(wid, name, sib) for sib in acts if sib != name and sib not in declared]
    return rows


ROWS = _text_field_acts()


def test_the_declarations_were_read():
    assert ("documento", "show", "goto") in ROWS, "the measured case is in the parametrized set"


@pytest.mark.parametrize("wid,action,sibling", ROWS)
def test_a_key_naming_a_sibling_action_is_never_folded_into_the_text_field(wid, action, sibling):
    field = C._spec(wid, action)["text_field"]
    out = C.fold_aliases(wid, action, {sibling: "Proof-of-Work"})
    assert field not in out, f"{wid}:{action} took `{sibling}` (an action of the same card) as its `{field}`"


def test_one_loose_text_that_names_no_action_still_folds():
    assert C.fold_aliases("documento", "show", {"content": "# A\n\ntext"})["body"] == "# A\n\ntext"


F2 = "go to the part about proof of work"
_F2_CALL = [{"name": "widget_data", "args": {"widget_id": "documento", "action": "show",
                                             "payload": {"goto": "Transactions and the chain"}}}]
_F2_BRIEF = {"screen_action": ["documento:goto", 0.99], "request_type": ["order", 0.9]}


def test_through_the_turn_the_verdict_goes_to_the_section_and_the_document_is_not_replaced():
    out = _voice_turn(F2, ["documento"], _F2_BRIEF, tools=_F2_CALL, lang="en")
    assert not _ran(out, "show"), "the call that fills no slot of `show` replaced the document"
    assert _ran(out, "goto"), out.decision


def test_the_disarm_the_fold_takes_any_loose_key_and_the_document_is_replaced(monkeypatch):
    """The sibling-action exclusion switched off: `goto` folds into `body` again and `show` runs over the verdict."""
    monkeypatch.setattr(C, "_names_an_action", lambda *_a, **_k: False)
    assert C.fold_aliases("documento", "show", {"goto": "x"}).get("body") == "x", "the mutation landed"
    out = _voice_turn(F2, ["documento"], _F2_BRIEF, tools=_F2_CALL, lang="en")
    assert _ran(out, "show"), out.decision


def test_the_verdict_goes_to_what_he_named():
    out = _voice_turn(F2, ["documento"], _F2_BRIEF, tools=_F2_CALL, lang="en")
    assert any("proof of work" in str((p or {}).get("text") or "").lower() for p in _ran(out, "goto")), _ran(out, "goto")


def test_the_disarm_a_call_that_fills_no_slot_still_runs_over_the_verdict(monkeypatch):
    """The arbitration half switched off: the unfolded `show {"goto": …}` runs, and the verdict's `goto` does not."""
    monkeypatch.setattr(C, "fills_no_slot", lambda *_a, **_k: False)
    assert C.fills_no_slot("documento", "show", {"goto": "x"}) is False, "the mutation landed"
    out = _voice_turn(F2, ["documento"], _F2_BRIEF, tools=_F2_CALL, lang="en")
    assert _ran(out, "show") and not _ran(out, "goto"), out.decision

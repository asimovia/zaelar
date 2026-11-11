"""V2-886 D1 — a durable question is one of two kinds, read from what its producer declared, never from its wording:
`consent` (an act waits for his yes — a card on screen, with its ✕) or `clarify` (a fact or a choice the work needs —
it waits on the row the same way, but it is DIALOGUE, said in the conversation, never a card).

Operator, 2026-11-11: «if it asks "play what?", that is not a card — it is part of the dialogue». The `ask` event
carries the kind, the board's waiting rows carry it after a reload, and the screen draws only `consent`."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from nucleo.circuit import asker

ENGINE = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("entry,kind", [
    ({"inline": True, "consent": "ask_consent", "retained": {"kind": "start"}}, "consent"),     # an errand's start
    ({"inline": True, "consent": "ask_consent", "retained": {"action": "delete"}}, "consent"),  # a card's delete (C13)
    ({"action": "widget_data", "retained": {"action": "widget_data", "payload": {}}}, "consent"),  # a worker's held act
    ({"action": "ask_user", "retained": {}}, "clarify"),                                       # a worker's own question
    ({"inline": True, "consent": "ask_fact", "retained": {"kind": "send_task", "action": "send_to"}}, "clarify"),
    ({"inline": True, "consent": "ask_which", "retained": {"action": "play"}}, "clarify"),
    ({"inline": True, "retained": {"kind": "notice"}}, "clarify"),                             # a reminder's question
    ({}, "clarify"), (None, "clarify"),
])
def test_the_kind_is_what_the_producer_declared(entry, kind):
    assert asker.kind_of(entry) == kind


def test_the_ask_event_and_the_board_carry_the_kind(monkeypatch):
    seen = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append(kw.get("extra") or {}))
    monkeypatch.setattr(asker, "_row", lambda tid: {})
    asker._on_bus({"topic": "worker.ask", "payload": {"task_id": "r", "ask_id": "q", "question": "?",
                                                      "kind": "consent"}})
    asker._on_bus({"topic": "worker.ask", "payload": {"task_id": "r", "ask_id": "q2", "question": "?"}})
    assert [e["ask_kind"] for e in seen] == ["consent", "clarify"]
    src = (ENGINE / "nucleo/circuit/ledger.py").read_text(encoding="utf-8")
    assert '"ask_kind": _asker.kind_of(' in src


def test_the_screen_draws_only_a_question_of_consent():
    js = (ENGINE / "frontend/app/core/asks.js").read_text(encoding="utf-8")
    assert 'if (d.ask_kind === "clarify") return;' in js and 'if (r.ask_kind === "clarify") return null;' in js

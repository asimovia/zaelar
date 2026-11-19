"""A go-ahead the owner does not take says WHICH guard refused it (INI-042 #44 P0a).

Measured 2026-11-18 (local session, the owner in place): two «Sí,» after the confirmation re-asked it, and the log could
not say why — six guards decided his yes and none left its reason. They live in ONE function now, `heard.answers`, and
each refusal carries its reason; the owner records it as `go-ahead not taken`. Invented people only.
"""
from __future__ import annotations

import pytest

from nucleo.send import draft as _draft
from nucleo.send import heard


def _ready(**kw) -> _draft.Draft:
    d = _draft.Draft(said="send Odile Marsh that I'm late", who="Odile", text="I'm late",
                     target={"name": "Odile Marsh", "contact_id": "c1", "platform": "whatsapp"})
    d.asked, d.confirm_line, d.heard, d.heard_at = _draft.CONFIRM, "Odile Marsh: «I'm late». Shall I send it?", True, 10.0
    for k, v in kw.items():
        setattr(d, k, v)
    return d


GO = {"send": True, "bare": False}
LAST = "Odile Marsh: «I'm late». Shall I send it?"


@pytest.fixture(autouse=True)
def _typed_line(monkeypatch):
    monkeypatch.setattr(heard, "began_before", lambda d: False)


def test_a_clear_go_ahead_after_the_confirmation_he_heard_is_taken():
    assert heard.answers(_ready(), GO, LAST, changed=False, ready=True) == (True, "")


@pytest.mark.parametrize("draft_kw, got, last, changed, ready, why", [
    ({}, {"send": False, "bare": True}, LAST, False, True, "did not take it as a go-ahead (a bare yes)"),
    ({}, GO, LAST, True, True, "also change the message"),
    ({}, GO, LAST, False, False, "nothing ready"),
    ({"heard": False}, GO, LAST, False, True, "has not heard"),
    ({"other_at": 20.0}, GO, LAST, False, True, "another line of ours"),
    ({}, {"send": True, "bare": True}, "Something else entirely.", False, True, "not our last line"),
])
def test_each_refusal_names_its_guard(draft_kw, got, last, changed, ready, why):
    ok, said = heard.answers(_ready(**draft_kw), got, last, changed=changed, ready=ready)
    assert not ok and why in said


def test_a_sentence_begun_before_the_confirmation_is_named(monkeypatch):
    monkeypatch.setattr(heard, "began_before", lambda d: True)
    ok, said = heard.answers(_ready(), GO, LAST, changed=False, ready=True)
    assert not ok and "began before" in said


def test_the_owner_records_the_refused_yes_with_its_reason(monkeypatch):
    """The owner's own path: the case measured on 2026-11-18 — a bare «Yes» the read did not take as a go-ahead is
    recorded as `go-ahead not taken` with its reason, and nothing leaves."""
    import asyncio
    import json

    from nucleo.send import deliver, owner, people, read
    reads = [json.dumps({"mine": True, "who": "Odile Marsh", "text": "I'm late", "channel": "", "send": False,
                         "drop": False, "list": ""}),
             json.dumps({"mine": True, "who": "", "text": None, "channel": "", "send": False, "bare": True,
                         "drop": False, "list": ""})]
    monkeypatch.setattr(read, "_ask", lambda system, user: reads.pop(0))
    monkeypatch.setattr(people, "resolve", lambda name, channel="", relation="": {
        "one": {"name": "Odile Marsh", "contact_id": "c1", "note": "", "platform": channel}})
    monkeypatch.setattr(people, "_in_front", lambda name: {})
    monkeypatch.setattr(deliver, "check", lambda d: {"ok": True, "platform": "whatsapp"})
    sent, emitted = [], []
    monkeypatch.setattr(owner, "_run", lambda d: sent.append(d) or {"ok": True})
    monkeypatch.setattr(owner, "_emit", lambda label, d, **extra: emitted.append((label, extra)))
    _draft.reset()
    try:
        asyncio.run(owner.intake("Tell Odile Marsh I'm late", {}))
        line = _draft.current().confirm_line
        owner.heard(line)
        taken, _ = asyncio.run(owner.take("Yes", last_line=line))
        assert taken and not sent
        refused = [x for label, x in emitted if label == "go-ahead not taken"]
        assert refused and "bare yes" in refused[-1]["why"], emitted
    finally:
        _draft.reset()

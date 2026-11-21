"""A confirmation he already heard is never read to him again (node 13.146, C3).

With the message's confirmation asked and heard, words of his that are neither a yes, a no nor a change are answered
in ONE short line that asks again — never the whole message read back, the parrot he complained of — and that short
line is now the confirmation his yes answers. A change to the message is read back whole, as before. Every worded
line speaks the way the conversation's prefix does: one style line for both (`style_policy.line`), and what a fact
asks to say whole (the message's text in its confirmation) is said whole whatever that style says (`wording.WHOLE`).
"""
from __future__ import annotations

import asyncio

from nucleo.send import ask, draft, owner


def _heard_draft():
    d = draft.Draft(said="w_tell ana goodnight", who="w_ana", text="w_goodnight", target={"name": "W_Ana"})
    d.asked, d.confirm_line, d.heard = draft.CONFIRM, "W_Ana: «w_goodnight». w_send it?", True
    return d


def _words(monkeypatch):
    seen = []

    async def line(key, lead="", **fmt):
        seen.append(key)
        return f"<{key}>"
    monkeypatch.setattr(ask, "line", line)

    async def confirm(*a, **k):
        seen.append("send_confirm")
        return "<the whole message>"
    monkeypatch.setattr(ask, "confirm", confirm)
    return seen


def test_words_that_are_neither_yes_nor_no_are_answered_short_and_become_the_question(monkeypatch):
    seen = _words(monkeypatch)
    d = _heard_draft()
    line = asyncio.run(owner._step(d, {"mine": True}, "", "w_you are repeating yourself"))
    assert line == "<send_still_asked>" and seen == ["send_still_asked"]
    assert d.confirm_line == line and d.heard is False and d.asked == draft.CONFIRM


def test_a_change_to_the_message_is_read_back_whole(monkeypatch):
    seen = _words(monkeypatch)
    monkeypatch.setattr("nucleo.send.deliver.check", lambda d: {"ok": True})
    d = _heard_draft()
    asyncio.run(owner._step(d, {"mine": True, "text": "w_goodnight and sleep well"}, "", "w_add sleep well"))
    assert "send_confirm" in seen and "send_still_asked" not in seen


def test_a_worded_line_speaks_the_way_the_prefix_does(monkeypatch):
    from nucleo import style_policy, wording
    from nucleo.conversation_host import prefix
    monkeypatch.setattr(style_policy, "line", lambda speech_style="": "w_short and plain")
    systems = []
    monkeypatch.setattr(wording, "_ask", lambda system, user, seat: systems.append(system) or "w_line")
    assert wording.word("w_a fact") == "w_line" and "HOW YOU SPEAK: w_short and plain" in systems[0]
    assert systems[0].endswith(wording.WHOLE), "what the fact asks to say whole beats the style (a confirmation)"
    assert prefix.style_line("w_x") == "w_short and plain"

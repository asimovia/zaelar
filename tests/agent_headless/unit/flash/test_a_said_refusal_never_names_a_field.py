"""A refusal said aloud never names a field or an action of the code.

Measured on a text session (2026-11-16): two `add_reminder` calls were refused with the card's `error` — «no moment to
ring at: notice_at is missing», a sentence written for the MODEL — and, every op of the turn being refused, the turn
handed that sentence to the line composer, which told him: «You'll need to add a notice_at value so I can run it
again.» The composer is now handed the reason without its code-shaped words, and a composed line that still carries
one is replaced by the plain failure line.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib

import pytest

from nucleo.flash import data_ops, refusal_line
from nucleo.workers import spoken_delivery


class _Sp:
    @staticmethod
    def sanitize(t, drop_metadata=False):
        return t


def _turn(error, composed=None, monkeypatch=None, mod=data_ops):
    seen = {}

    async def _line(goal, summary, ok=True, **_k):
        seen["handed"] = summary
        return composed if composed is not None else summary
    monkeypatch.setattr(spoken_delivery, "line", _line)
    sent, done = [], {"v": True}

    async def go():
        async def op():
            return {"ok": False, "error": error}
        return await mod.say_refusal_instead([("agenda", asyncio.ensure_future(op()))], done, sent.append, _Sp)
    return asyncio.run(go()), seen.get("handed", ""), done


@pytest.mark.parametrize("error, names", [
    ("no moment to ring at: notice_at is missing", ["notice_at"]),
    ("la hoja no lleva contenido — vuelve a llamar a set_body con `body` ('body' vacío)", ["set_body", "`"]),
    ("missing {start_time} for move_meeting", ["start_time", "move_meeting", "{"]),
])
def test_the_composer_is_never_handed_a_name_of_the_code(monkeypatch, error, names):
    said, handed, done = _turn(error, monkeypatch=monkeypatch)
    assert handed and not any(n in handed for n in names), handed
    assert said and not any(n in said for n in names) and done["v"] is False, said


def test_a_composed_line_that_names_one_anyway_is_replaced_by_the_plain_line(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    said, _handed, _done = _turn("no moment to ring at", "You'll need to add a notice_at value so I can run it again.",
                                 monkeypatch=monkeypatch)
    assert said == data_ops._failed_line() and "notice_at" not in said, said


def test_a_reason_in_plain_words_is_still_said(monkeypatch):
    said, handed, _done = _turn("no tengo el Telegram de Rowan", "I couldn't send it — I don't have Rowan's Telegram.",
                                monkeypatch=monkeypatch)
    assert handed == "no tengo el Telegram de Rowan" and "Rowan" in said


def test_what_counts_as_code():
    assert refusal_line.codey("add a notice_at value") and refusal_line.codey("use `body`")
    assert not refusal_line.codey("I couldn't set that reminder — it has no time yet.")
    assert refusal_line.without_code("no moment to ring at: notice_at is missing") == "no moment to ring at: is missing"


def test_disarmed_the_field_is_said_again(monkeypatch):
    src = pathlib.Path(data_ops.__file__)
    original = src.read_text(encoding="utf-8")
    guard = "        if _rline.codey(said):\n            said = _failed_line()\n"
    assert guard in original, "the bound on the composed line is not where this disarm expects it"
    try:
        src.write_text(original.replace(guard, ""), encoding="utf-8")
        mutated = importlib.reload(data_ops)
        said, _h, _d = _turn("no moment to ring at", "Add a notice_at value.", monkeypatch=monkeypatch, mod=mutated)
        assert "notice_at" in said, "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("data_ops.*.pyc"):
            pyc.unlink()
        importlib.reload(data_ops)
    said, _h, _d = _turn("no moment to ring at", "Add a notice_at value.", monkeypatch=monkeypatch)
    assert "notice_at" not in said

"""A refusal said aloud never names a field or an action of the code — the card's `error` never reaches the mouth.

Measured on a text session (2026-11-16): two `add_reminder` calls were refused with the card's `error` — «no moment to
ring at: notice_at is missing», a sentence written for the MODEL — and, every op of the turn being refused, the turn
handed that sentence to a line composer, which told him: «You'll need to add a notice_at value so I can run it
again.» Taking the code-shaped words out of it first leaves the rest of an instruction to the model («call again
with…») and every field that is one plain word (`date`, `payload`, `startTime`).

The rule is the one every other refusal already follows (`reply.of_op`, V2-652): what he hears is the card's own
`say`/`message`; a refusal with neither is the mouth's plain line, and its `error` stays on the timeline.
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


def _turn(res, monkeypatch, mod=data_ops):
    composed, traced = [], []

    async def _line(goal, summary, ok=True, **_k):
        composed.append(summary)
        return f"You'll need to fix this: {summary}"
    monkeypatch.setattr(spoken_delivery, "line", _line)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: traced.append(k.get("text", "")))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    sent, done = [], {"v": True}

    async def go():
        async def op():
            return res
        return await mod.say_refusal_instead([("agenda", asyncio.ensure_future(op()))], done, sent.append, _Sp)
    return asyncio.run(go()), composed, done, traced


@pytest.mark.parametrize("error", [
    "no moment to ring at: notice_at is missing",
    "la hoja no lleva contenido — vuelve a llamar a set_body con `body` ('body' vacío)",
    "falta startTime: pasa date y time en payload",                  # one-word and camelCase fields: no shape to catch
    "la lista no lleva nombre — vuelve a llamar con el nombre; NO inventes uno",   # an instruction to the model
    "no tengo el canal de Ilse Brandt",
])
def test_the_cards_error_is_never_said_nor_handed_to_a_composer(monkeypatch, error):
    said, composed, done, traced = _turn({"ok": False, "error": error}, monkeypatch)
    assert said == data_ops._failed_line() and said, said
    assert not composed, f"the error was handed to a composer: {composed}"
    assert done["v"] is False and any(error[:40] in t for t in traced), "the turn is not done, and the reason is kept for us"


def test_a_refusal_with_the_cards_own_sentence_is_the_mouths_and_carries_it(monkeypatch):
    """The reminder with no moment: the card ASKS in its own words, so this door has nothing to stand in for."""
    from nucleo.turn import reply
    from widgets.agenda import notice
    res = notice._a_add_reminder("add_reminder", {"title": "water the ferns"}, {}, {})
    said, composed, done, _traced = _turn(res, monkeypatch)
    assert said == "" and not composed and done["v"] is True
    line = reply.of_op("agenda", "add_reminder", res).reason
    assert line and "?" in line and "notice_at" not in line and line != res["error"], line


def test_disarmed_the_error_is_said_again(monkeypatch):
    src = pathlib.Path(data_ops.__file__)
    original = src.read_text(encoding="utf-8")
    plain = "        said = _failed_line()          # the mouth's own line"
    assert plain in original, "the plain line is not where this disarm expects it"
    try:
        src.write_text(original.replace(plain, "        said = why[1]          # the mouth's own line"), encoding="utf-8")
        mutated = importlib.reload(data_ops)
        said, _c, _d, _t = _turn({"ok": False, "error": "notice_at is missing"}, monkeypatch, mod=mutated)
        assert "notice_at" in said, "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("data_ops.*.pyc"):
            pyc.unlink()
        importlib.reload(data_ops)
    said, _c, _d, _t = _turn({"ok": False, "error": "notice_at is missing"}, monkeypatch)
    assert "notice_at" not in said


def test_the_readers_that_took_code_words_out_are_gone():
    assert not hasattr(refusal_line, "without_code") and not hasattr(refusal_line, "codey")

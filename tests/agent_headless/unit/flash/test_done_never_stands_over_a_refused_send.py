"""«Done.» never stands over a turn whose every op was refused with a reason nobody says (demo pass 104, 2026-10-04).

C5 «send rowan a telegram with the new time»: `send_to` was refused («no tengo el Telegram de Rowan» — an internal
`error`, addressed to the model, so `report_failure` only leaves it as a note for the NEXT turn) and, the model
having said nothing, the canned success ack spoke «Done.» ten milliseconds later. The operator was told a message
went out that never did. The ack now waits for this turn's ops; when all of them were refused unsaid, the reason
is said instead.
"""
from __future__ import annotations

import asyncio


def _run(results, delay=0.0):
    from nucleo.acts import data_ops

    async def go():
        async def op(r):
            await asyncio.sleep(delay)
            return r
        tasks = [("mensajeria", asyncio.ensure_future(op(r))) for r in results]
        return await data_ops.refused_unsaid(tasks, timeout=1.0)
    return asyncio.run(go())


def test_an_internal_refusal_is_returned_to_be_said():
    why = _run([{"ok": False, "error": "no tengo el Telegram de Rowan"}], delay=0.2)
    assert why and "Telegram" in why[1], why


def test_a_success_keeps_the_ack():
    assert not _run([{"ok": True}])
    assert not _run([{"ok": True}, {"ok": False, "error": "x"}]), "one op landed — the ack is not a lie"


def test_a_refusal_the_widget_already_speaks_is_not_said_twice():
    assert not _run([{"ok": False, "error": "x", "message": "There are no more videos."}])


def test_an_op_still_running_past_the_wait_keeps_todays_path():
    assert not _run([{"ok": False, "error": "x"}], delay=2.0)


def test_the_turn_says_it_was_not_done_and_is_no_longer_done(monkeypatch):
    """The refusal is said in the mouth's plain line; the `error` is the model's and is never composed into words
    (2026-11-17 — a channel he lacks is said by the card's own `say`, `widgets.mensajeria.refusal_no_channel`)."""
    from nucleo.acts import data_ops
    from nucleo.workers import spoken_delivery
    async def _line(goal, summary, ok=True, **_k):
        raise AssertionError("the card's error was handed to a composer")
    monkeypatch.setattr(spoken_delivery, "line", _line)
    sent, done = [], {"v": True}

    class _Sp:
        @staticmethod
        def sanitize(t, drop_metadata=False): return t

    async def go():
        async def op():
            return {"ok": False, "error": "no tengo el Telegram de Rowan"}
        return await data_ops.say_refusal_instead([("mensajeria", asyncio.ensure_future(op()))], done, sent.append, _Sp)
    said = asyncio.run(go())
    assert said and sent == [said] and done["v"] is False and "Telegram" not in said

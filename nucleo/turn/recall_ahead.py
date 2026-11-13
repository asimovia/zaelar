"""The durable recall starts with the turn's brief, beside it, and the brief decides whether the turn waits for it (V2-903).

Until V2-903 a regex of ~150 expressions decided whether a turn recalled (`recall_heuristics.needs_recall`), and the
recall ran IN SERIES before the model call, up to its 800 ms budget. Measured on the audit: it fired on 14 of 20 everyday
Spanish sentences («pon música de Queen» by «de que», «abre la agenda»), on 6 of 14 English ones, and on none of a real
memory question in Japanese. A word table was routing, and every firing was paid before the first word.

Now there is no router:

  · `launch(text)` starts the recall (both halves, `recall_budget.start`) at the EARLIEST moment the sentence is known —
    the eager end of turn the ear announces (with the brief, `brief_turn.fire_early`), else admission. Keyed by the
    sentence as said, like the brief, so the admitted turn finds the one already flying.
  · the brief carries one question, `KEY`: does answering need something durable about him?
  · `take(...)` is what the prompt reads: the recall if it ARRIVED; otherwise it waits — bounded by what is left of the
    budget since the launch — until it arrives or the brief says, sure at the VETO floor, that the turn needs none.

A recall that arrived is used: it was free. An unsure or absent verdict waits (a false «none» is an amnesic answer, the
expensive mistake). Started at the eager end of turn, most recalls have landed before the turn is confirmed.
"""
from __future__ import annotations

import time

from loguru import logger

#: The brief's question (`nucleo/turn/brief.QUESTIONS`) — its key, owned here with its only reader.
KEY = "durable_memory"
REMEMBER, NONE = "remember", "none"
INSTRUCTIONS = ("To answer or carry out this turn well, is anything needed that the operator told us before or that we "
                "did together earlier, and that this sentence alone does not carry?")
CRITERIA = {
    REMEMBER: "yes: a fact about him or someone close to him, a place, a preference, a habit («the usual», «my "
              "dentist»), a past event, or something said or done earlier in our conversations",
    NONE: "no: a greeting, a thanks, an answer to our question, or an order or question about the world that nothing "
          "he told us before would change",
}


def question() -> dict:
    return {"instructions": INSTRUCTIONS, "criteria": dict(CRITERIA)}


#: Recalls started for a sentence before its prompt was built: `{key: Pending}`. Bounded; a stale one is not reused.
_AHEAD: dict = {}
_MAX = 4


def _key(text: str) -> str:
    from nucleo.turn import brief_turn
    return brief_turn._key(text)


def launch(text: str, *, live_turns: int | None = None):
    """Start the recall for this sentence now, once. Returns the pending recall, or None. Never raises."""
    key = _key(text)
    if not key:
        return None
    have = _AHEAD.get(key)
    if have is not None and have.left_s() > 0:
        return have
    try:
        from nucleo.turn import recall_budget
        pending = recall_budget.start(text, live_turns)
    except Exception as e:  # noqa: BLE001 — the turn starts its own at the prompt, as before
        logger.debug(f"recall_ahead: not launched — {e!r}")
        return None
    if pending is not None:
        _AHEAD[key] = pending
        while len(_AHEAD) > _MAX:
            _AHEAD.pop(next(iter(_AHEAD)))
    return pending


def not_needed(brief) -> bool:
    """The brief says, sure at the VETO floor, that this turn needs no durable memory. In flight or unsure → False."""
    try:
        from nucleo.turn import verdicts
        state, choice = verdicts.sure(brief, KEY, verdicts.VETO)
        return state == verdicts.SURE and choice == NONE
    except Exception as e:  # noqa: BLE001 — unreadable reads as «may need it»: the turn waits, as it used to
        logger.debug(f"recall_ahead: verdict unread — {e!r}")
        return False


async def take(text: str, brief=None, timings: dict | None = None, *, live_turns: int | None = None):
    """`(recall_block, ids)` for this turn's prompt: the recall launched for this sentence (or one started now), waited
    for only while the brief has not said the turn needs none, and never past its budget. Never raises."""
    t0 = time.monotonic()
    key = _key(text)
    pending = _AHEAD.pop(key, None) if key else None
    if pending is not None and pending.left_s() <= 0 and not pending.done():
        pending = None                                      # a launch that aged out: this turn starts its own
    if pending is None:
        pending = launch(text, live_turns=live_turns)
        _AHEAD.pop(key, None)
    from nucleo.turn import recall_budget
    if timings is not None:
        timings["recall_fired"] = pending is not None
        timings["recall_ahead"] = bool(pending is not None and pending.done())
    got = await recall_budget.deliver(pending, timings, not_needed=lambda: not_needed(brief))
    if timings is not None:
        timings["recall_wait_ms"] = round((time.monotonic() - t0) * 1000, 1)
    return got


def _reset_for_tests() -> None:
    _AHEAD.clear()

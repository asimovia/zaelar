"""nucleo/turn/items_asked.py — several entries asked, one written: the mouth says the rest is not done.

Measured on a text session (2026-11-16): «Also add: Tuesday 9am team standup, Wednesday 3pm coffee with Sam, Thursday
6pm piano lesson, and Sunday 11am brunch with the family.» → the model made ONE call (`agenda:add_meeting`, the
standup), it landed, and the reply was «Done.». Three appointments were never written and nothing said so; two turns
later the model, reading its own «Done.» in the window, told him the coffee «is already in there». The same day «Make
me a shopping list: oat milk, avocados, …» ran `add_list` with a name and no items, and «Done.» stood over an empty
list.

`acts_asked` cannot see this: the same thing done to several entries is ONE act by its own definition (a bulk call is
one call). How many ENTRIES his words name is its own question of the brief (`items_asked`, any language, never a word
list), asked at the same door — the turn's first model call. When the brief is sure he named several and the model
made exactly one call, carrying no list, that landed as the turn's only op, the mouth says only part was done and
where: the verdict is `unmet`, always said, and it takes the place of the «Done.» that used to follow.

What it does not reach: several asked and SOME written (two calls for four entries) — the brief answers one or
several, not how many.
"""
from __future__ import annotations

from loguru import logger

KEY = "items_asked"
ONE, SEVERAL = "one", "several"

INSTRUCTIONS = ("How many separate NEW entries does the operator ask to be created or added in this message, in any "
                "wording or language? An entry is one thing of its own to write down: one appointment, one reminder, "
                "one task, one note, one contact, one line of a list. Count the entries he names, not the verbs: "
                "«add A on Monday, B on Tuesday and C on Friday» is three entries under one verb, and a list asked "
                "for together with the things that go in it is several. Several details of ONE entry (its day, its "
                "hour, its place, who comes) are one entry. Changing, moving, marking or deleting entries that "
                "already exist creates nothing.")
CRITERIA = {
    ONE: "one new entry, or nothing to create at all (a question, a chat, a show, a play, a search, a change or a "
         "removal of what already exists)",
    SEVERAL: "two or more separate new entries to create or add, each with its own name, day or hour",
}


def question(_ctx=None) -> dict:
    """Asked at the CALL door (`brief_doors.DOORS["call"]`), in the same trip as `acts_asked`, whose `owed` waits for
    that trip and reads both."""
    return {"instructions": INSTRUCTIONS, "criteria": dict(CRITERIA)}


def several(brief) -> bool:
    """The brief is SURE (veto confidence: this reading makes the mouth say something was not done) he named more
    than one new entry."""
    try:
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, KEY, None, min_confidence=verdicts.VETO)
        return bool(info) and choice == SEVERAL
    except Exception as e:  # noqa: BLE001 — unread is «not sure»: nothing is said
        logger.debug(f"items_asked: verdict unread — {e!r}")
        return False


def _carries_a_list(value) -> bool:
    """A call whose arguments hold a list of two or more carries several entries by itself (a list with its items)."""
    if isinstance(value, (list, tuple)):
        return len(value) > 1 or any(_carries_a_list(v) for v in value)
    if isinstance(value, dict):
        return any(_carries_a_list(v) for v in value.values())
    return False


def one_single_call(model_calls) -> bool:
    """The model made exactly one call this turn and it names one entry."""
    calls = [c for c in model_calls or () if isinstance(c, dict) and c.get("name")]
    return len(calls) == 1 and not _carries_a_list(calls[0].get("args"))


def left_undone(tasks=(), model_calls=None, *, brief=None) -> list:
    """The `unmet` outcome owed when he named several new entries and the turn wrote one; [] otherwise."""
    try:
        if len(list(tasks or ())) != 1 or not one_single_call(model_calls):
            return []
        if brief is None:
            from nucleo.turn import brief_turn
            brief = brief_turn.of_this_turn()
        if not several(brief):
            return []
        from i18n import langs
        from nucleo.circuit import verdict as V
        from nucleo.flash import card_receipt
        from nucleo.turn.reply import Outcome
        card, _sep, action = str(list(tasks)[0][0]).partition("::")
        tpl = str(getattr(langs.current_language(), "reply_part_only", "") or "")
        if not tpl:
            return []
        line = tpl.format(cards=card_receipt.card_name(card))
        return [Outcome(V.UNMET.name, card, action, reason=line, said=line)]   # `reason`: never silent (`acts_asked`)
    except Exception as e:  # noqa: BLE001 — never takes the reply down
        logger.debug(f"items_asked: not read — {e!r}")
        return []

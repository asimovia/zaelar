"""nucleo/turn/unserved.py — an act the turn's words claim and no door of the turn ran is said undone (CRIT-V12).

Measured in the use-case battery of 2026-11-06, in both languages and on several cards:

- «Mejor avísame ese día a mediodía» → the model called `agenda:set_reminder` and streamed «Cambio el aviso a las
  doce…»; the call was diverted (the card was neither open nor named, the row did not resolve) and ended in a card
  READ of another card; no op touched the agenda, and the narration stood as the turn's line.
- «there's no class next Tuesday, take off just that day» → ZERO calls, «I've cancelled just next Tuesday's piano».
- «Exit full screen.» over an empty canvas → ZERO calls, «but I've cleared it, so you're at an empty canvas now».

The class: the mouth composes the turn's line from the verdicts of the acts that RAN (`reply.after_acts`), so an act
that never reached a door has no verdict and nothing corrects the words that narrated it. Three readers close it, all
read off what the turn already paid for, never off the words:

1. **A model call nobody ran.** A `widget_data` call the model made whose card no op and no card act of the turn
   touched — not asked about, not held for his yes, not routed to a task (a routed turn never reaches the mouth) —
   is `unmet`: the card's act did not happen. A card that acted this turn (the verdict completed or replaced the
   call, CRIT-K2) owes nothing here.
2. **A sure order no door served.** The brief read an ORDER that does not owe words (`wants_words` ≠ tell), aimed at
   a card or at the canvas (`catalog_widget`, `screen_action` or `canvas` name one), the model called nothing and the
   turn's doors ran nothing, and the turn did not end asking him: `unmet`, nothing was done. A comment («note that I'm
   celiac» reads `comment`), a question, or any call at all keeps the model's words alone.

3. **A sure order served on ANOTHER card.** The same sure order names ONE card (`catalog_widget`, or the card of
   `screen_action`); the model did call something, but no call of the turn addresses that card and no door touched
   it, and no data-op ran at all — it opened a panel, showed another card — and the turn did not end asking: `unmet`, nothing was done there.
   Measured in a sandbox with no channel connected: «write to <name> on whatsapp: …» → `show_panel` (the connectors)
   and «Done.» (1 of 12, V2-909 F1).

The lines are the verdict's (`reply_not_run`, `reply_nothing_done`), always said after the model's words — a fact
the model could not know, never a re-run and never a sentence about how to behave.
"""
from __future__ import annotations

from loguru import logger

#: A reply whose last character is one of these closes on a question — punctuation, never vocabulary
#: (`nucleo/request/ask_outside_door`).
_QUESTION_MARKS = "?？؟"


#: Turns whose model words WAIT behind an act (the hold deferred them to the turn's end), by trace: such a turn has
#: said nothing YET and is not a silent one.
_WAITING: dict[str, bool] = {}


def waiting(text: str = "") -> str:
    """Record that this turn's words wait; returns them (the hold keeps what it defers)."""
    from nucleo.turn import reply
    _WAITING[reply._trace()] = True
    if len(_WAITING) > 32: _WAITING.pop(next(iter(_WAITING)))   # noqa: E701 — a bounded record of recent turns
    return text


def words_waiting() -> bool:
    from nucleo.turn import reply
    return reply._trace() in _WAITING


def _ended_asking(said: str) -> str:
    last = str(said or "").rstrip().rstrip("»\"'”)")[-1:]
    return bool(last) and last in _QUESTION_MARKS      # a turn that said nothing asked nothing


def _cards_that_acted(tasks) -> set[str]:
    """The base ids of the cards the turn's doors touched: its data-ops and its card acts (shows, closes, controls)."""
    from nucleo.request import base
    try:
        from nucleo.turn import acts_asked
        return {base(card) for card, _action in acts_asked.ran(tasks)}
    except Exception as e:  # noqa: BLE001 — unread is «nothing ran»; the callers' other gates still apply
        logger.debug(f"unserved: the turn's acts were not read — {e!r}")
        return set()


def calls_not_run(model_calls, tasks) -> list[tuple[str, str]]:
    """`[(card, action)]` — the `widget_data` calls the model made this turn on a card no door of the turn touched,
    one per card, in the order the model made them."""
    from nucleo.request import base
    acted = _cards_that_acted(tasks)
    out: list[tuple[str, str]] = []
    for c in model_calls or ():
        if not isinstance(c, dict) or c.get("name") != "widget_data":
            continue
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        card, action = base(args.get("widget_id")), str(args.get("action") or "").strip()
        if not card or not action or card in acted or any(card == w for w, _a in out):
            continue
        try:   # a read that did not run has no act to say undone; a send is its worker task's (V2-931)
            from widgets import effects
            if effects.carries(card, action, effects.DATA_READ) or effects.leaves(card, action):
                continue
        except Exception as e:  # noqa: BLE001 — an unreadable manifest reads as an act
            logger.debug(f"unserved: {card}:{action} effects unread — {e!r}")
        out.append((card, action))
    return out


def order_unserved(brief) -> bool:
    """The brief read a sure-enough ORDER (at the licence) that owes no words and aims at a card or the canvas."""
    try:
        from nucleo.turn import brief as tb, verdicts
        kind, k_info = verdicts.read(brief, tb.REQUEST_KEY, None)
        if not k_info or str(kind or "") != "order":
            return False
        words, w_info = verdicts.read(brief, tb.WORDS_KEY, None)
        if w_info and str(words or "") == "tell":
            return False
        for key in (tb.CATALOG_KEY, tb.TARGET_KEY, tb.CANVAS_KEY):
            choice, info = verdicts.read(brief, key, None)
            # a choice that names nothing (the questions' declared «none» / the canvas's «neither») aims at nothing
            if info and str(choice or "").strip().lower() not in ("", "none", "neither"):
                return True
        return False
    except Exception as e:  # noqa: BLE001 — unread is «not an order»: nothing is said
        logger.debug(f"unserved: the brief was not read — {e!r}")
        return False


def ordered_card(brief) -> str:
    """The base id of the ONE card a sure order aims at (`catalog_widget`, else the card of `screen_action`); '' when
    it names none, or the canvas."""
    try:
        from nucleo.request import base
        from nucleo.turn import brief as tb, verdicts
        for key in (tb.CATALOG_KEY, tb.TARGET_KEY):
            choice, info = verdicts.read(brief, key, None)
            card = base(str(choice or "").partition(":")[0])
            if info and card not in ("", "none", "neither"):
                return card
    except Exception as e:  # noqa: BLE001 — unread names no card: nothing is said
        logger.debug(f"unserved: the ordered card was not read — {e!r}")
    return ""


def _addresses(call, card: str) -> bool:
    """Does this model call address `card` — by any argument naming it, or as the tool that drives it?"""
    from nucleo.acts.media import CARD_OF_TOOL
    from nucleo.request import base
    if not isinstance(call, dict):
        return False
    if CARD_OF_TOOL.get(call.get("name")) == card:
        return True
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    return any(isinstance(v, str) and base(v) == card for v in args.values())


def served_elsewhere(brief, tasks, model_calls) -> bool:
    """A sure order names ONE card, no data-op ran this turn (what the model did was show or open something), and
    neither a call of the model nor a door of the turn touched that card. A turn that WROTE somewhere else served the
    order its own way: its doors' verdicts speak for it."""
    if tasks or not order_unserved(brief) or not (card := ordered_card(brief)):
        return False
    return card not in _cards_that_acted(tasks) and not any(_addresses(c, card) for c in model_calls or ())


def outcomes(tasks, model_calls, *, said: str, quiet: bool, held: bool = False, brief=None) -> list:
    """The `unmet` outcomes the turn owes for what its words may claim and its doors did not run. `quiet`: the turn's
    doors ran nothing at all (no op, no card act, no lane, no worker); `held`: the turn holds an act for his yes or
    asks which row — nothing is undone then, it waits."""
    try:
        from i18n import langs
        from nucleo import canvas_focus as _cf
        from nucleo.circuit import verdict as V
        from nucleo.play import shadow as _play
        from nucleo.turn import reply as _reply
        if held or _reply.asked() or _ended_asking(said) or (words_waiting() and not str(said or "").strip()):
            return []      # …or the model's words WAIT behind an act (the hold's deferred words): they are its answer
        lang, out = langs.current_language(), []
        missed = calls_not_run(model_calls, tasks)
        if missed:
            tpl = str(getattr(lang, "reply_not_run", "") or "")
            if tpl:
                from nucleo.flash import card_receipt
                for card, action in missed:
                    line = tpl.format(cards=card_receipt.card_name(card))
                    out.append(_reply.Outcome(V.UNMET.name, card, action, reason=line, said=line))
                    _play.line(card, action, V.UNMET.name)      # shadow: an outcome claimed for a live programme
            return out
        if brief is None:
            from nucleo.turn import brief_turn
            brief = brief_turn.of_this_turn()
        called = any(isinstance(c, dict) and c.get("name") for c in model_calls or ())
        if (quiet and not called) or (called and served_elsewhere(brief, tasks, model_calls)):
            if order_unserved(brief) and not _cf.this_turn_writes():   # a card written in the background is served (F1)
                line = str(getattr(lang, "reply_nothing_done", "") or "")
                if line:
                    out.append(_reply.Outcome(V.UNMET.name, "", "", reason=line, said=line))
        return out
    except Exception as e:  # noqa: BLE001 — never takes the reply down
        logger.debug(f"unserved: not read — {e!r}")
        return []

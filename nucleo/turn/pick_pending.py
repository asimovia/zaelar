"""nucleo/turn/pick_pending.py — the deferred choice and the screen↔errand arbiter, in SHADOW (V2-878 §5).

Measured on a demo turn: «abre el que sea mejor oferta» while a monitors search ran with NO rows yet. Today a card
always wins the turn (`stop.card_owns_the_turn`), and a choice about rows that do not exist yet has nowhere to live:
it is relayed to the worker as a note and forgotten, so when the rows land nobody picks.

Three readings, each a cross of verdicts already paid — no vocabulary, no model call — and each only EMITTED here:

  · `noted`        — at the portal (`flow_door.obey`), a request routed into an errand (`inject`/`steer`) whose sheet
                     has no rows, from a turn that does not ask to be TOLD (`wants_words` is not `tell`), is a choice to
                     make when the rows arrive: the card of that errand carries `pick_pending` (his words, when). The
                     relay itself runs exactly as before.
  · `at_first_rows`— when the first rows land on that errand's sheet (`first_rows_notice.landed`, the sheet's door),
                     what WOULD be relayed to the worker («the rows are here: choose by …»). Nothing is relayed.
  · `arbiter`      — whose turn is it, by consequence: rows on screen his reference can land on → the card; the
                     errand he names has no rows and holds a deferred choice → the errand; both → ask which. Emitted
                     beside what the owner rule did, so a week of `would ≠ did` can be read before it acts.

A shadow never changes the turn: every function returns nothing the caller uses to decide, and never raises.
"""
from __future__ import annotations

import time

from loguru import logger

#: The card key the deferred choice is written under (the errand's row, `progress.card`).
KEY = "pick_pending"
#: trace → what this turn's portal noted (the commission's shadow reads it at the close).
_TURN: dict[str, dict] = {}
#: errand uids whose first rows were already reported (one «would relay» per errand).
_REPORTED: set[str] = set()


def _trace() -> str:
    try:
        from voice import trace
        return str(trace.current() or "")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pick_pending: no trace — {e!r}")
        return ""


def _rows(sheet: str) -> int:
    try:
        from nucleo.flash.errand_sheet import rows_of_sheet
        return len(rows_of_sheet(str(sheet or ""), 1)) if sheet else 0
    except Exception as e:  # noqa: BLE001 — unreadable rows read as «some»: a shadow never claims a gap it cannot see
        logger.debug(f"pick_pending: rows of {sheet} unreadable — {e!r}")
        return 1


def _wants(brief) -> str:
    try:
        from nucleo.turn import brief as _tb
        return str(_tb.read(brief, _tb.WORDS_KEY, "")[0] or "") if brief is not None else ""
    except Exception as e:  # noqa: BLE001 — an unreadable verdict reads as «not tell»: the shadow notes, nothing acts
        logger.debug(f"pick_pending: wants_words unreadable — {e!r}")
        return ""


def _uid(flow_id: str) -> str:
    from nucleo.turn import named_errand
    return named_errand._uid_of(str(flow_id or ""))


def noted(req: str, r: dict, brief=None) -> dict | None:
    """The portal routed `req` into errand `r["flow"]`: write the deferred choice on its card when it has no rows and the
    turn does not ask to be told. Returns what was noted (None when nothing). The route's consequence is untouched."""
    try:
        if str((r or {}).get("as") or "") not in ("inject", "steer") or _rows(r.get("sheet") or "") > 0:
            return None
        if _wants(brief) == "tell":
            return None
        uid = _uid(r.get("flow") or "")
        if not uid:
            return None
        pick = {"heard": " ".join(str(req or "").split())[:300], "at": int(time.time())}
        from nucleo.circuit import ledger
        ledger.card_written(uid, **{KEY: pick})
        note = {"flow": str(r.get("flow") or ""), "uid": uid, **pick}
        _TURN[_trace()] = note
        while len(_TURN) > 32:
            _TURN.pop(next(iter(_TURN)))
        from nucleo.turn import thread_event
        thread_event.pick_pending(note, shadow=True)
        return note
    except Exception as e:  # noqa: BLE001 — a shadow never breaks a portal
        logger.debug(f"pick_pending: not noted — {type(e).__name__}: {e}")
        return None


def of_turn() -> dict:
    """What this turn's portal noted, for the commission's shadow: {} when nothing."""
    return dict(_TURN.get(_trace()) or {})


def at_first_rows(sheet: str, errand: dict | None) -> dict | None:
    """The first rows landed on `errand`'s sheet: what WOULD be relayed to its worker. Once per errand; relays nothing."""
    try:
        uid = _uid(str((errand or {}).get("id") or ""))
        if not uid or uid in _REPORTED:
            return None
        from nucleo.circuit import ledger
        pick = (ledger.card(uid) or {}).get(KEY) or {}
        if not pick.get("heard"):
            return None
        _REPORTED.add(uid)
        from nucleo.turn import thread_event
        return thread_event.would_relay(uid, str(sheet or ""), pick)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pick_pending: first rows not read — {type(e).__name__}: {e}")
        return None


def _rows_on_screen(brief) -> bool:
    """A row his reference can land on: an open card that lists rows."""
    try:
        from widgets import refs
        open_ids = list((brief or {}).get("open_ids") or []) if isinstance(brief, dict) else []
        return any(refs._ref_index(str(w).split("::", 1)[0]) for w in open_ids)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pick_pending: rows on screen unreadable — {e!r}")
        return False


def arbiter(brief, text: str, *, card_owns: bool) -> dict | None:
    """Whose turn it would be, by consequence — `card` · `errand` · `ask` · `none` — emitted beside `did` (today's owner
    rule, `card_owns`). Once per turn. Returns the emitted verdict; the caller's decision never reads it."""
    t = _trace()
    if not t or t in _ARBITRATED:
        return None
    _ARBITRATED.add(t)
    while len(_ARBITRATED) > 64:
        _ARBITRATED.pop()
    try:
        from nucleo.turn import named_errand
        card = bool(card_owns) and _rows_on_screen(brief)
        named = named_errand.strongest(str(text or "")) if text else None
        pick = ((__import__("nucleo.circuit.ledger", fromlist=["x"]).card(_uid(named["id"])) or {}).get(KEY)
                if named else None)
        errand = bool(pick) and _rows(named.get("sheet") or "") == 0
        would = "ask" if card and errand else "card" if card else "errand" if errand else "none"
        did = "card" if card_owns else "errand"
        from nucleo.turn import thread_event
        return thread_event.arbitrated(would, did, flow=str((named or {}).get("id") or ""), heard=text)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pick_pending: arbiter unreadable — {type(e).__name__}: {e}")
        return None


_ARBITRATED: set[str] = set()


def reset() -> None:
    _TURN.clear()
    _REPORTED.clear()
    _ARBITRATED.clear()

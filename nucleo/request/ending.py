"""nucleo/request/ending.py — «acted» is the request's `done_when` met: a view never ends a request about a send (V2-851 F2e).

Measured after F2d: «send Rachel a message…» — the model first called `mensajeria:show_view` (a lens), the data-op door
settled the turn's row `done` with an `undeclared` verdict, and then the reply asked «which Rachel?». The row had
ended, so the question could not wait on it (an ended row is never re-opened), and the turn counted as acted, so
`ask_outside_door` never measured it. A request about an act that LEAVES ends on that act's echo, never on a view, a
draft or a show of the same card.

The rule, at the one door every inline data-op crosses (`nucleo/acts/data_ops.dispatch_and_report`), for an act that
does NOT leave the machine on a card that DECLARES acts that do (`widgets.effects.leaves`), and that only shows or
prepares (a lens — no `data.write` — or an act that mounts the card, a draft; never one that answers):

  · inside a live turn, its ending is written when the turn closes (`close_turn`) — unless the same turn
    ran one of the card's leaving acts on that row (that act writes the end), or the turn ended
    on our own question about that card's leaving act, which makes the row WAIT instead (`ask_outside_door.held`)
    (`hold` → `TURN`). An op that lands after its turn closed writes its ending at once, unless the row now waits;
    a turn whose end never comes writes what it held after `STALE_S`.

`only_held()` tells the turn's end that every data-op it ran was one of these, so the question about the leaving act
is measured and made durable as if nothing had acted. Reads declared effects only — never his words.
"""
from __future__ import annotations

from nucleo.request import base, model, note

TURN = "turn"
#: A turn whose end never came (a path that did not reach `close_turn`) writes what it held after this long.
STALE_S = 30.0


def leaving_acts(wid: str) -> list[str]:
    """The card's declared acts that leave the machine."""
    try:
        from widgets import effects
        card = base(wid)
        return sorted(a for a in (effects._manifest(card).get("actions") or {}) if effects.leaves(card, a))
    except Exception as e:  # noqa: BLE001
        note(e)
        return []


def hold(wid: str, action: str, row: str) -> str:
    """How this op's ending is written: "" as always, `TURN` when its turn closes. Counts the op."""
    turn = model.current()
    how, leaves = "", False
    try:
        from widgets import effects
        leaves = effects.leaves(base(wid), action)
        # Held only when the act merely shows the card or prepares on it (a lens, a draft it mounts) — never a write of
        # its own, a send or an answer. Read off the declared effects.
        fx = effects.of(base(wid), action)
        shows_or_prepares = not (effects.EXTERNAL_SEND in fx or effects.OUTPUT_ANSWER in fx) and (
            effects.PRESENT_MOUNT in fx or (effects.DATA_READ in fx and effects.DATA_WRITE not in fx))
        if row and not leaves and shows_or_prepares and leaving_acts(wid):
            if turn is not None and not turn.get("closed"):
                how = TURN
    except Exception as e:  # noqa: BLE001 — unreadable: the op writes its ending as always
        note(e)
        how = ""
    if turn is not None:
        if row and not how and leaves:
            turn.setdefault("left", set()).add(str(row))     # the row's end is this act's: a held view never writes it
        turn["ops"] = int(turn.get("ops") or 0) + 1
        if how:
            turn["held_ops"] = int(turn.get("held_ops") or 0) + 1
    return how


def _waits(row: str) -> bool:
    try:
        from nucleo.circuit import ledger
        return str((ledger.get(row) or {}).get("state") or "") == "waiting"
    except Exception as e:  # noqa: BLE001
        note(e)
        return False


def defer(row: str, write) -> None:
    """Write an op's ending (`write()`) when its turn closes; at once when the turn already closed — never over a
    row that now waits on our question."""
    turn = model.current()
    if turn is not None and not turn.get("closed"):
        turn.setdefault("endings", []).append((str(row or ""), write))
        if not turn.get("armed"):
            turn["armed"] = True
            import threading
            t = threading.Timer(STALE_S, close_turn, args=(turn,))
            t.daemon = True
            t.start()
        return
    if not _waits(row) and str(row or "") not in ((turn or {}).get("left") or ()):
        write()


def close_turn(turn: dict | None = None) -> int:
    """The turn is over: write the endings it held, except over a row that now waits. How many were written."""
    turn = turn if turn is not None else model.current()
    if turn is None:
        return 0
    turn["closed"] = True
    n = 0
    left = turn.get("left") or set()
    for row, write in turn.pop("endings", []) or []:
        if _waits(row) or row in left:
            continue                             # the row waits on our question, or a leaving act writes its end
        try:
            write()
            n += 1
        except Exception as e:  # noqa: BLE001
            note(e)
    return n

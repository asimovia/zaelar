"""The canvas door: every card the engine shows or closes on his screen crosses `apply` (refactor2710-04 T-02).

A writer names the act, the card and its provenance (`src`, the arbiter's closed set). A show or close is judged by its
provenance first and its verdict emitted armed (`arbiter`, with `verdict` and `source`); a veto never reaches the canvas
and `apply` says so. Other ops cross the same door unjudged, so there is one writer either way.
"""
from __future__ import annotations

from nucleo.acts import arbiter_event as _record, canvas_arbiter as _arb, canvas_turn as _turn
from voice import canvas_src

#: The ops the arbiter licenses; every other op crosses the door as it is.
JUDGED = ("show", "close")


def apply(op: str, wid: str = "", *, src: str, text: str = "", role: str = "", emit=None, **extra) -> bool:
    """Put `op` on `wid` if the arbiter allows its provenance; True when the canvas was told. `wid=""` closes every
    card; `emit` the caller's stream (observer)."""
    op = (op or "").strip().lower()
    fields = ({"id": wid} if wid else {}) | {"src": src} | extra
    if op in JUDGED:
        v = _arb.decide(op, wid, src, action=str(extra.get("action") or ""))
        _record.emit_verdict(op, wid, src, str(extra.get("action") or ""), v, shadow=False)
        if not v.allow and v.rule != "arbiter-error" and not canvas_src.is_report(src):
            return False
        if op == "show" and __import__("nucleo.circuit", fromlist=["x"]).a_step_not_a_show(src, wid, emit=emit):
            return False       # refactor2710-15: an errand shows only its deliverable; its steps stay off his screen
    op == "show" and extra.get("action") and __import__("nucleo.done_ops", fromlist=["x"]).note(wid, str(extra["action"]), extra.get("payload") or {})   # a show CARRYING an act is a card act (V2-831 T-19)
    emit = emit or __import__("voice.observer", fromlist=["emit"]).emit
    fields["seq"] = _issue(op, wid, fields)   # V2-907 T5 (shadow): the order waits for its screens' answers
    with _turn.judged():
        emit("widget", op, **({"text": text} if text else {}), **({"role": role} if role else {}), extra=fields)
    __import__("nucleo.done_ops", fromlist=["x"]).gesture(op, wid)   # a gesture of his turn is «what we just did» (T-02c)
    __import__("nucleo.acts.surface_owner", fromlist=["x"]).observe(op, wid, src)   # V2-844 F0: whose it would be
    op == "show" and __import__("nucleo.chat_refs", fromlist=["x"]).note_show(src, wid)   # V2-862: an errand's card
    return True


def _issue(op: str, wid: str, fields: dict) -> int:
    """Record the order in the screen ledger with the screens that must answer it: the asking screen for an op scoped
    to its origin (`voice.screens.scope_of`, the server's copy of `event-scope.js`), else every open screen whose
    document lists the card (every one that lists any, for a close of all). 0 when the ledger cannot take it."""
    from loguru import logger
    from voice import screens
    from widgets import screen_doc, screen_orders
    try:
        if screens.scope_of("widget", op) == "origin":
            targets = [o] if (o := screens.origin_of(fields)) else []
        elif wid:
            targets = screen_doc.screens_of(wid)
        else:
            targets = [s["dev"] for s in screens.open_screens() if screen_doc.open_ids(s["dev"])]
        return screen_orders.issue(op, wid, targets)
    except Exception as e:  # noqa: BLE001 — the ledger is a witness: an order it cannot record still goes out
        logger.warning(f"canvas: order {op} {wid or '*'} not recorded in the screen ledger ({e!r})")
        return 0

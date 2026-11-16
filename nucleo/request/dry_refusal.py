"""nucleo/request/dry_refusal.py — a send task the card would refuse as asked is said in the turn, before any promise.

Measured: «mándale un WhatsApp a Ana diciendo que llego tarde» with WhatsApp not connected — the turn said «you'll have
it in a moment», the row ended `failed`, and a notice later asked for «her number», never saying the channel was off.
The card's own dry reading (`widgets.contract.would_refuse`, its `would_refuse` hook: a channel down) runs when the
task's slots are complete and before it is scheduled; a refusal ends the row `cannot` with its line, said now.
"""
from __future__ import annotations

from nucleo.request import base, note


def said(uid: str, wid: str, action: str, art: dict) -> bool:
    """The card's own dry reading of the act (`contract.would_refuse`): a refusal ends the row now and is SAID in
    this turn — never a «you'll have it in a moment» and a failed row later."""
    try:
        from widgets import contract
        refusal = contract.would_refuse(base(wid), action, dict(art.get("payload") or {}))
    except Exception as e:  # noqa: BLE001 — unread: the act runs and its own door refuses it
        note(e)
        return False
    line = str((refusal or {}).get("message") or "").strip()
    if not line:
        return False
    from nucleo import circuit
    circuit.settle(row=uid, verdict="cannot", outcome=line[:300])
    from nucleo.request.send_task import _said_asked
    _said_asked(wid, action, line)
    return True

"""The two items of the ledger and THE table of their valid transitions. This table is the only source: a move it
does not list is refused (`InvalidTransition`) and said (`conv_ledger/refused`).

  request     what the person asked; survives a superseded run and is what liveness counts (I9)
  effect      the reservation of one logical effect: written before it is sent, never re-sent. Whether it was
              delivered is the receipt of the connector that sent it, not a state of this row.

Tasks, their questions, what is owed, mandates and receipts are rows of the host, each with its own writer: the
conversation refers to them by id and keeps no copy.
"""
from __future__ import annotations

from conversation.types import ItemKind as K


class InvalidTransition(ValueError):
    pass


INITIAL: dict[K, str] = {K.REQUEST: "open", K.EFFECT: "claimed"}

TRANSITIONS: dict[K, dict[str, frozenset[str]]] = {
    K.REQUEST: {"open": frozenset({"answered", "handed_off", "silent", "recovered", "failed"})},
    K.EFFECT: {"claimed": frozenset({"submitting", "withdrawn"}),   # claimed = provably not sent;
                                                                     # withdrawn = a stop or a failed run left it
               "submitting": frozenset({"provider_accepted", "rejected", "submission_unknown"}),
               "submission_unknown": frozenset({"provider_accepted", "rejected"})},     # reconciliation, never a resend
}


def final(kind: K, state: str) -> bool:
    return state not in TRANSITIONS[kind]


def check(kind: K, frm: str, to: str) -> None:
    if to not in TRANSITIONS[kind].get(frm, frozenset()):
        raise InvalidTransition(f"{kind}: {frm} → {to} is not in the table")

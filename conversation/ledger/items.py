"""The items of the ledger and THE table of their valid transitions (§6.4). This table is the only source: a move it
does not list is refused (`InvalidTransition`) and said (`conv_ledger/refused`).

  request     what the person asked; survives a superseded run (N1) and is what liveness counts (I9)
  task        work with an owner (`conversation` or `worker:<id>`)
  question    ours, waiting for an answer; a focus candidate only once PRESENTED
  grant       a permission given when he commissioned something: the exact content or a bounded template
  handle      a one-use confirmation: recipient, channel, exact text, question, expiry
  delegation  hands-free scope, created only by a gesture on the device (D8)
  effect      one logical effect; reconciliation never re-sends
  followup    waiting for a reply after a send — its own item, apart from the effect (C2)
  to_tell     something owed to the person; `deferred` is not an end, it carries its next due time
"""
from __future__ import annotations

from conversation.types import ItemKind as K


class InvalidTransition(ValueError):
    pass


INITIAL: dict[K, str] = {
    K.REQUEST: "open", K.TASK: "started", K.QUESTION: "asked", K.GRANT: "active", K.HANDLE: "issued",
    K.DELEGATION: "active", K.EFFECT: "claimed", K.FOLLOWUP: "waiting", K.TO_TELL: "pending",
}

TRANSITIONS: dict[K, dict[str, frozenset[str]]] = {
    K.REQUEST: {"open": frozenset({"answered", "handed_off", "silent", "recovered", "failed"})},
    K.TASK: {"started": frozenset({"running", "waiting", "failed", "cancelled"}),
             "running": frozenset({"waiting", "done", "failed", "cancelled"}),
             "waiting": frozenset({"running", "done", "failed", "cancelled"})},
    K.QUESTION: {"asked": frozenset({"presented", "expired", "superseded"}),
                 "presented": frozenset({"answered", "expired", "superseded"})},
    K.GRANT: {"active": frozenset({"spent", "expired", "revoked"})},
    K.HANDLE: {"issued": frozenset({"presented", "expired"}),
               "presented": frozenset({"spent", "expired"})},
    K.DELEGATION: {"active": frozenset({"exhausted", "expired", "revoked"})},
    K.EFFECT: {"claimed": frozenset({"submitting"}),          # claimed = provably not sent (plan §15 E4)
               "submitting": frozenset({"provider_accepted", "rejected", "submission_unknown"}),
               "submission_unknown": frozenset({"provider_accepted", "rejected"}),     # reconciliation, never a resend
               "provider_accepted": frozenset({"delivered", "delivery_unconfirmed", "failed"})},
    K.FOLLOWUP: {"waiting": frozenset({"matched", "expired"})},
    K.TO_TELL: {"pending": frozenset({"told", "coalesced", "expired", "deferred"}),
                "deferred": frozenset({"pending", "told", "coalesced", "expired"})},
}


def final(kind: K, state: str) -> bool:
    return state not in TRANSITIONS[kind]


def check(kind: K, frm: str, to: str) -> None:
    if to not in TRANSITIONS[kind].get(frm, frozenset()):
        raise InvalidTransition(f"{kind}: {frm} → {to} is not in the table")

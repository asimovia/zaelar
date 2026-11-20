"""The conversation's record — «what did I tell you yesterday» (v3.1 §1.8): one pair per answered batch, what
he said and what we answered, handed to the host's `Record` port AT LEAST once. The pair is owed in the store
(`records`, state `owed`) before it is handed over and marked `done` after; the sweep and a recovery hand over what is
still owed, so a crash between the two leaves at most a repeated pair in a record that expires anyway.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation.types import EnvelopeKind

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation

TABLE = "records"
CONTENT = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)


def owe(conv: "Conversation", run_id: str, envelopes, answered: str) -> None:
    if conv.record is None:
        return
    said = " ".join(e.body.text for e in envelopes if e.is_user and e.kind in CONTENT and e.body.text)
    with conv.store.tx(conv.lease) as tx:
        tx.put(TABLE, run_id, {"state": "owed", "said": said, "answered": answered, "t_ms": conv.clock.now_ms()})
    hand_over(conv)


def hand_over(conv: "Conversation") -> int:
    """Hand every owed pair to the port; a port that fails keeps it owed for the next sweep. Returns how many went."""
    if conv.record is None:
        return 0
    with conv.store.tx(conv.lease) as tx:
        owed = tx.scan(TABLE, states=("owed",))
    went = 0
    for key, row in owed:
        try:
            conv.record.pair(conv.account, row["said"], row["answered"], ref=key)
        except Exception as e:  # noqa: BLE001 — the record lags; the pair stays owed and the sweep tries again
            conv.em.emit("conv_close", "record_failed", owner="manager", cause={"kind": "record"}, refs={"run": key},
                         error=f"{type(e).__name__}: {str(e)[:120]}")
            continue
        with conv.store.tx(conv.lease) as tx:
            tx.put(TABLE, key, {**row, "state": "done"})
        went += 1
    return went

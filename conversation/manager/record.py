"""The conversation's record — «what did I tell you yesterday» (v3.1 §1.8): one pair per answered batch, what
he said and what he HEARD us answer — written when our line ends, with what sounded of it: a line cut at its fourth
word is four words here, and one whose sound is unknown is nothing (what was never pronounced does not exist for the
conversation; the whole reply stays in observability only). Handed to the host's `Record` port AT LEAST once. The pair is owed in the store
(`records`, state `owed`) before it is handed over and marked `done` after; the sweep and a recovery hand over what is
still owed, so a crash between the two leaves at most a repeated pair in a record that expires anyway.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation.mouth.say import SAYS
from conversation.types import EnvelopeKind

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation

TABLE = "records"
CONTENT = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)


def owe(conv: "Conversation", run_id: str, envelopes, say_id: str) -> None:
    """The pair of a batch our line `say_id` answers: it waits for that line to end (`heard`)."""
    if conv.record is None:
        return
    said = " ".join(e.body.text for e in envelopes if e.is_user and e.kind in CONTENT and e.body.text)
    with conv.store.tx(conv.lease) as tx:
        tx.put(TABLE, run_id, {"state": "waiting", "said": said, "say": say_id, "answered": "",
                               "t_ms": conv.clock.now_ms()})
    heard(conv, say_id)


def heard(conv: "Conversation", say_id: str) -> None:
    """Our line ended: its pair is owed with what SOUNDED of it — the line cut where its voice was cut, nothing when its
    sound is unknown."""
    if conv.record is None or not say_id:
        return
    view = conv.store.view(conv.account)
    line = view.get(SAYS, say_id)
    if line is None or line["state"] != "ended":
        return
    waiting = [(k, r) for k, r in view.scan(TABLE, ("waiting",)) if r.get("say") == say_id]
    if not waiting:
        return
    n = line.get("heard_chars")
    answered = line["text"][:n] if n is not None else ""
    with conv.store.tx(conv.lease) as tx:
        for k, r in waiting:
            tx.put(TABLE, k, {**r, "state": "owed", "answered": answered})
    hand_over(conv)


def hand_over(conv: "Conversation") -> int:
    """Hand every owed pair to the port; a port that fails keeps it owed for the next sweep. Returns how many went."""
    if conv.record is None:
        return 0
    owed = conv.store.view(conv.account).scan(TABLE, ("owed",))         # a read: idle opens no transaction
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

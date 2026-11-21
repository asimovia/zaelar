"""His controls at the conversation's doors (V2-941, v3.1 B10): a stop from a BUTTON is an envelope of its own; a
stop he says or types is no control here — his words reach the model, which chooses a stop order (plan v3.2 §3), and
no word of his is read on the manager's path. And his phrase a device's own ear caught (the browser's wake word): VOICE,
an entry of its own, never typed and never the old turn. And the switch turned off: the conversation this process
opened retires, with no restart.
"""
from __future__ import annotations

import time
import uuid

from nucleo.conversation_host import entry, line_cut


#: where a stop came from → its producer and channel (the package refuses a control from anyone else)
STOP_BY = (("chat", "chat:", "text"), ("ear", "ear:", "voice"), ("button", "button:", "button"))


def control(op: str = "stop", dev: str = "", by: str = "chat") -> None:
    """His control (today a stop, from a button): an envelope of its own. No word of his is read to make one."""
    t = int(time.time() * 1000)
    entry._hand(lambda conv: conv.give(make(conv, op, dev or "holder", by, t)))


def make(conv, op: str, endpoint: str, by: str, t: int):
    """His control as the package takes it: an envelope from its door's producer, on its door's channel."""
    from conversation import envelopes as E
    from conversation.types import Channel, ControlOp, EnvelopeKind
    prefix, channel = next(((p, c) for b, p, c in STOP_BY if b == by), ("chat:", "text"))
    return E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp(op), gesture=by == "button"),
                  producer=f"{prefix}{endpoint}", producer_id=f"k_{uuid.uuid4().hex[:12]}", account=conv.account,
                  onset_ms=t, sealed_ms=t, channel=Channel(channel), endpoint=endpoint)


#: a phrase the device's own ear caught is the paid ear's turn when the paid ear brought its words this recently
HEARD_WITHIN_S = 10.0
HEARD_BY_EAR = "heard_by_ear"


def local_phrase(text: str, dev: str = "") -> None:
    """His phrase a device's own ear caught (the browser's wake word): VOICE into the ear, an entry of its own — unless
    the paid ear already brought those words (its own turn, a few seconds ago or in course): then it is discarded
    `heard_by_ear` and never enters, so the same words are never answered twice, nor do they cut our reply."""
    from conversation.ear import signals as S
    from nucleo.conversation_host import ear_in
    from voice import echo_text
    if not str(text or "").strip():
        return
    if any(echo_text.contained(text, heard) for heard in ear_in.heard_lately(HEARD_WITHIN_S)):
        where = dev or "holder"
        entry._hand(lambda c: c.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "device_ear"},
                                        refs={"endpoint": where, "channel": "voice"}, trace=f"local:{where}",
                                        text=str(text)[:400], reason=HEARD_BY_EAR))
        return
    sig = S.LocalPhrase(dev or "holder", f"l_{uuid.uuid4().hex[:12]}", line_cut.clipped(text, dev),
                        int(time.time() * 1000))
    entry._hand(lambda c: c.hear(sig))


def retire_if_off() -> bool:
    """Switched off (the account's key removed, the environment cleared): the conversation this process opened stops —
    its thread and its sweep — without a restart. Off every caller's loop: stopping waits for the thread. True: retired."""
    from nucleo.conversation_host import sessions, switch
    with entry._lock:
        live = entry._opener["rt"] is not None
    if not live or switch.decide(None).on:
        return False
    sessions.close_all()
    entry.reset()
    return True

"""His controls at the conversation's doors (V2-941, v3.1 B10): a stop — typed, spoken or a button — is an envelope
of its own, handed ahead of whatever he said with it; the package reads no words (the detector that heard «stop»
lives in the engine, `guards.orders_stop`). And his phrase a device's own ear caught (the browser's wake word): VOICE,
an entry of its own, never typed and never the old turn. And the switch turned off: the conversation this process
opened retires, with no restart.
"""
from __future__ import annotations

import time
import uuid

from nucleo.conversation_host import entry


#: where a stop came from → its producer and channel (the package refuses a control from anyone else)
STOP_BY = (("chat", "chat:", "text"), ("ear", "ear:", "voice"), ("button", "button:", "button"))


def control(op: str = "stop", dev: str = "", by: str = "chat") -> None:
    """His control (today a stop): an envelope of its own, ahead of whatever he said with it. The package reads no
    words: the detector that heard «stop» lives outside it (`attention.is_shut_up`)."""
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


def local_phrase(text: str, dev: str = "") -> None:
    """His phrase a device's own ear caught (the browser's wake word): VOICE into the ear, an entry of its own."""
    from conversation.ear import signals as S
    if not str(text or "").strip():
        return
    sig = S.LocalPhrase(dev or "holder", f"l_{uuid.uuid4().hex[:12]}", str(text).strip()[:4000],
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

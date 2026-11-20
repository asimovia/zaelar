"""Typed input: an intervention that is CLOSED the moment it is sent (§6.2). No turn detection and no reopening —
a second message is another intervention, and the model sees both. The 0.35 s debounce is the inbox's collect
window, not the ear's."""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation import envelopes as E
from conversation.ear.signals import LocalPhrase, TypedSubmit
from conversation.types import Channel, EnvelopeKind

if TYPE_CHECKING:
    from conversation.ear.arbiter import Ear


def phrase(ear: "Ear", sig: LocalPhrase, t: int) -> E.Envelope:
    """A device's own ear heard his phrase: one closed VOICE entry of its own (its grace is a voice's, unmarked)."""
    iv = ear.ids.new("iv")
    env = E.make(EnvelopeKind.USER_UTTERANCE, E.UtteranceBody(iv, sig.text), producer=f"ear:{sig.endpoint}",
                 producer_id=f"{iv}:local:{sig.client_id}", account=ear.account, onset_ms=t, sealed_ms=t,
                 channel=Channel.VOICE, endpoint=sig.endpoint, refs=E.Refs(intervention_id=iv))
    ear.em.emit("conv_ear", "local_phrase", owner="ear", cause={"kind": "device_ear", "ref": sig.client_id},
                refs={"iv": iv, "endpoint": sig.endpoint, "channel": "voice"}, closed_by="device_ear")
    return env


def submit(ear: "Ear", sig: TypedSubmit, t: int) -> E.Envelope:
    iv = ear.ids.new("iv")
    env = E.make(EnvelopeKind.USER_TEXT, E.TextBody(iv, sig.text), producer=f"chat:{sig.endpoint}",
                 producer_id=sig.client_id, account=ear.account, onset_ms=t, sealed_ms=t, channel=Channel.TEXT,
                 endpoint=sig.endpoint, refs=E.Refs(intervention_id=iv))
    ear.em.emit("conv_ear", "typed", owner="ear", cause={"kind": "client", "ref": sig.client_id},
                refs={"iv": iv, "endpoint": sig.endpoint, "channel": "text"}, closed_by="submit")
    return env

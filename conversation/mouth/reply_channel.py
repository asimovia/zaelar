"""Which channels answer a batch (§7.1): a deterministic rule over the batch's channels and the device's state —
it never reads what was said. The chat column ALWAYS gets the text (it is the record of the conversation, V7);
the voice is the extra decision.

  batch with voice      voice live and speaker open → voice + text; otherwise text, and `voice_unavailable`
  batch of text only    voice live and speaker open ON THAT DEVICE → voice + text when the operator's rule says so
                        (the default keeps today's behaviour, PA-9); otherwise text
A line owed (a result, a contact's message, a reminder) is not a batch: it is already on the wall and goes by voice.
"""
from __future__ import annotations

from dataclasses import dataclass

from conversation import envelopes as E
from conversation.types import EnvelopeKind


@dataclass(frozen=True)
class Device:
    endpoint: str | None
    voice_live: bool = False
    speaker_open: bool = False
    blocked: bool = False


@dataclass(frozen=True)
class Reply:
    channels: frozenset[str]
    voice_unavailable: bool = False


TEXT, VOICE = frozenset({"text"}), frozenset({"voice", "text"})


def choose(batch: tuple[E.Envelope, ...], device: Device, *, text_gets_voice: bool = True) -> Reply:
    can_speak = device.voice_live and device.speaker_open and not device.blocked
    kinds = {e.kind for e in batch}
    if EnvelopeKind.USER_UTTERANCE in kinds:
        return Reply(VOICE) if can_speak else Reply(TEXT, voice_unavailable=True)
    return Reply(VOICE if (can_speak and text_gets_voice) else TEXT)

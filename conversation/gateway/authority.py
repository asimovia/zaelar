"""I8: what a run may do is judged per tool call from the run's batch — never from the model.

In F1 the gateway lets a read pass and refuses everything else. What stays for the reservation (F2's door, exercised
today only by its own tests) is the batch's AUTHORITY FLOOR: an effect rests on the person's entries, the first by
onset being its trigger, and a batch that carries anything else lends no authority at all. The `on` the model may
name is an attribution hint for telemetry and nothing more.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from conversation import envelopes as E
from conversation.types import EnvelopeKind

CONTENT = frozenset({EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT})


@dataclass(frozen=True)
class RunCtx:
    run_id: str
    request_id: str
    batch: dict[str, E.Envelope]                  # env id → envelope (the manager's, never the model's)
    endpoint: str | None = None                   # the device the run answers
    interventions: dict[str, int] = field(default_factory=dict)


def op_key(tool: str, args: dict) -> str:
    return f"{tool}:{json.dumps(args, sort_keys=True, separators=(',', ':'))}"


def effect_id(mandate: str, trigger: str, op: str) -> str:
    return "x_" + hashlib.sha256(f"{mandate}|{trigger}|{op}".encode()).hexdigest()[:20]


def floor(ctx: RunCtx) -> list[E.Envelope] | None:
    """The person's entries an effect rests on, by onset — or None when the batch carries anyone else's."""
    content = [e for e in ctx.batch.values() if e.kind in CONTENT]
    if not content or any(not e.is_user for e in content):
        return None
    return sorted(content, key=lambda e: (e.onset_ms, e.accepted_ms, e.id))

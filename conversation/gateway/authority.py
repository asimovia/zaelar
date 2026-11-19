"""I8: authority is judged PER EFFECT, from the run's batch — never from the model (plan §15 E1).

The manager hands the gateway the batch of the run. Its AUTHORITY FLOOR:
  · every entry with content is the person's (`user.*`) → an effect rests on those entries; the trigger is the first
    by onset (a voice + text batch is fine);
  · any `contact`, `worker` or `system` entry in the batch → no implicit authority at all: an effect needs, one by
    one, a presented handle spent by a gesture, a delegation, or a grant for that exact operation.
A batch that mixes the person's sentence with a contact's message lends the contact nothing (A3). The `on` the model may name
is an attribution hint for telemetry and nothing more.

Mandates (ledger items):
  handle      one-use confirmation of ONE bound effect, presented and then spent by a GESTURE (`confirm`, gesture)
  delegation  hands-free scope for `egress`, created only by a gesture (D8): recipients, channel, expiry, a maximum
  grant       created only through the ledger API from an all-user batch AND an active delegation that covers its
              recipient and channel, bound to the exact operation (plan §15 E6)
`destructive` and `payment` always need a gesture. A text is not a gesture (PA-10).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from conversation import envelopes as E
from conversation.ports import ToolSpec
from conversation.types import EffectClass, EnvelopeKind, ItemKind

ITEMS = "items"
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


def bound(spec: ToolSpec, args: dict) -> dict:
    """recipient · channel · content of an effect, read through the tool's declared binding."""
    return {role: args.get(arg) for role, arg in spec.binding.items()}


def needs_gesture(spec: ToolSpec) -> bool:
    return spec.effect_class in (EffectClass.EGRESS, EffectClass.DESTRUCTIVE, EffectClass.PAYMENT)


def delegation_for(tx, spec: ToolSpec, args: dict, now: int) -> dict | None:
    if spec.effect_class is not EffectClass.EGRESS:
        return None
    b = bound(spec, args)
    for _k, row in tx.scan(ITEMS):
        if row["kind"] != str(ItemKind.DELEGATION) or row["state"] != "active":
            continue
        d = row["data"]
        if (b.get("recipient") in d.get("recipients", ()) and b.get("channel") == d.get("channel")
                and now < d.get("expires_ms", 0) and d.get("used", 0) < d.get("max", 0)):
            return row
    return None


def grant_for(tx, tool: str, args: dict, now: int) -> dict | None:
    """A grant matches its exact operation only (plan §15 E6)."""
    op = op_key(tool, args)
    for _k, row in tx.scan(ITEMS):
        if (row["kind"] == str(ItemKind.GRANT) and row["state"] == "active" and row["data"].get("op") == op
                and now < row["data"].get("expires_ms", 0)):
            return row
    return None

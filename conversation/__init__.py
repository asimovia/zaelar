"""The conversation & turn manager — an isolated package (V2-941).

One manager per account decides WHEN: when the person finished an intervention, what enters the model's turn, what
waits, what is said and through which channel. WHAT to do is the model's: no code in front of it picks a tool, a task
or the source of an answer. Everything outside comes in through seven ports (`ports.py`); the package imports
nothing of the engine — only the standard library (node 13.1).

Pieces (each a folder, each a box of the architecture map):
  ear/       the arbiter of the voice intervention (open → extended → closed, reopened, incomplete) and typed input
  inbox/     the durable mailbox: accept, dedupe, one order across channels (by onset), collect, account for all
  ledger/    the items of what is open (request, task, question, grant, handle, delegation, effect, follow-up…)
  composer/  a pure function: snapshot + batch → the prompt (NOW · OPEN · TO_TELL · CONVERSATION · INPUT)
  gateway/   the only producer of effects: seal per revision, authority per effect, outbox, holds
  mouth/     say, acks per device, what was heard, the reply channel
  manager/   the policy table, the focus, the model's commands, one run, the loop, numeric claims

Design: `.meshkore/docs/modules/zaelar-conversation.md`. Adapter facts: `zaelar-conversation-adapter.md`.
"""
from conversation.config import Config
from conversation.envelopes import SCHEMA, Envelope, EnvelopeError, Refs
from conversation.types import Authority, Channel, EnvelopeKind, Ids

__all__ = ["SCHEMA", "Authority", "Channel", "Config", "Envelope", "EnvelopeError", "EnvelopeKind", "Ids", "Refs"]

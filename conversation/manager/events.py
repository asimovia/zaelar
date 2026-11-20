"""A batch that is one EVENT of the world (R-2): no model of the conversation runs for it. The host's router already
decided its route before it entered; its run hands it to the host's `Events` door, which carries the route out by the
doors that already do it, and the event is accounted and its request closed exactly once — `answered` when the door did
something, `silent` when there was nothing to do, `failed` when the door failed or was late. A door that fails never
owes him a line: the event is not his words.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation import guard
from conversation.inbox.mailbox import Batch
from conversation.types import EnvelopeKind

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation

#: what the door answers when it did nothing (the event is counted, and closed silent)
NOTHING = "nothing"


def request_of(env) -> str:
    """The request an event opens in the ledger, by its envelope."""
    return f"ev_{env.id}"


def is_event_batch(batch: Batch) -> bool:
    return bool(batch.envelopes) and all(e.kind is EnvelopeKind.EVENT for e in batch.envelopes)


async def run_event_batch(conv: "Conversation", batch: Batch) -> None:
    from conversation.manager import run
    for env in batch.envelopes:
        run_id = conv.ids.new("run")
        refs = {"run": run_id, "req": request_of(env)}
        conv.em.emit("conv_run", "started", owner="manager", cause={"kind": "event", "ref": env.id}, refs=refs,
                     batch_envs=[env.id], reason=batch.reason, origin=env.body.origin)
        try:
            if conv.events is None:
                raise LookupError("no Events port")
            outcome = str(await guard.call(conv.em, conv.cfg, "tools", conv.events.run(conv.account, env),
                                           conv.cfg.tool_ms, {"run": run_id}) or NOTHING)
            to, label = ("answered", "answered") if outcome != NOTHING else ("silent", "silent")
        except Exception as e:  # noqa: BLE001 — a door that fails ends the event visibly, and owes him nothing
            outcome, to, label = f"{type(e).__name__}", "failed", "failed"
        conv.inbox.account([env.id], {"answered": "told", "silent": "silent"}.get(to, "failed"), conv.clock.now_ms(),
                           reason=outcome)
        run.close(conv, request_of(env), to, label, None, reason=outcome)
        conv.em.emit("conv_run", "ended", owner="manager", cause={"kind": "event", "ref": env.id}, refs=refs,
                     outcome=to, reason=outcome, origin=env.body.origin)

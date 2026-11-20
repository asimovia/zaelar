"""A stop the model ordered (plan v3.2 §3): its first-order rule, the host's hands, and the `stopped` close.

The orders and their scopes are `commands.Stop`; the run (`run.py`) hands each one here and goes on, or ends, as the
scope says. No word of his is read: the model chose the stop from what he said.
"""
from __future__ import annotations

from conversation import guard
from conversation.manager import commands
from conversation.ports import ToolCall, ToolResult

STOP_NOT_FIRST = "a stop is your first order, before any read: this one stops nothing — reply or no_reply"
STOPPED = "stopped"                     # a batch the model closed with a stop and nothing more (and its fixed line)


def take(conv, r, order: commands.Stop, steps: list) -> bool:
    """A stop the model ordered. Valid only as its FIRST order in this run and before any read it asked for (what a page
    or a mail brought cannot stop anything); otherwise refused and counted. Valid: our voice is cut now and the line it
    cut is never resumed (`voice`, `run`, `all`), and the host is handed the control in the act (`Stops`). True when
    valid."""
    from conversation.manager.run import PSEUDO, _emit
    asked = [c for c, _res in steps if c.call_id not in PSEUDO]      # a read it asked for, refused or not
    if r.ordered or r.stopped or asked:
        _emit(conv, "command", r, command="stop_refused", scope=order.scope.value,
              reason="after_read" if asked else "not_first")
        steps.append((ToolCall("orders", "orders_check", {}), ToolResult("refused", data={"reason": STOP_NOT_FIRST})))
        return False
    r.stopped = order.scope.value
    if order.scope in commands.SILENCES:
        conv.speaker.stop(None, "stop", conv.clock.mono_ms(), trace=r.trace)
    if conv.stops is not None:
        guard.sync(conv.em, conv.cfg, "stops", lambda: conv.stops.stop(order.scope.value, r.ctx.endpoint))
    _emit(conv, "command", r, command="stop", scope=order.scope.value)
    return True


async def stopped(conv, r) -> None:
    """The batch closes `stopped`: nothing is said — but a batch only typed gets the language's fixed minimal line
    (`stopped`), on the text channel, so a typed order is never met with nothing."""
    from conversation.manager import hold
    from conversation.manager.run import _emit, _line, _typed_only, close
    if commands.Scope(r.stopped) in commands.SILENCES:
        hold.drop(conv, r.stopped)              # a reply waiting for his voice is never said after his stop
    now, said = conv.clock.now_ms(), False
    users = [e for e in r.ctx.batch.values() if e.is_user]
    line = _line(conv, STOPPED, r) if users and _typed_only(r) else ""
    if line and conv.gw.seal_publication(r.ctx, [e.refs.intervention_id for e in users]):
        await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text=line, channels=frozenset({"text"}),
                               endpoint=r.ctx.endpoint, trace=r.trace, iv=users[0].refs.intervention_id,
                               origin=STOPPED)
        said = True
    conv.inbox.account(list(r.batch_ids), "silent", now, reason=STOPPED)
    for req in r.requests:
        close(conv, req, "silent", STOPPED, r, reason=r.stopped)
    _emit(conv, "ended", r, outcome=STOPPED, scope=r.stopped, said=said)

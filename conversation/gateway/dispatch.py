"""Reads and actions through the `Tools` port. An action is submitted ONCE and never retried blind (A5).

Before `Tools.call` of an action — the last point the manager controls — one transaction checks again: the lease
(fencing, I5), the writes switch, the effect still `claimed` (never resubmitted from any other state), its mandate
not revoked or expired, and no hold received since it was claimed (A7). Then the effect moves to `submitting` and
commits BEFORE the call (the write-ahead, plan §15 E4). Whatever comes back maps to one state; an exception or a timeout is `submission_unknown`,
which keeps its slot and is reconciled by looking, never by sending again.
"""
from __future__ import annotations

import asyncio

from conversation.gateway import holds as H
from conversation.gateway.outbox import FLAGS, Gateway
from conversation.ports import ToolCall, ToolResult, Tools
from conversation.types import EffectClass, ItemKind



def _settled(status: str) -> str:
    """The provider's answer → the effect's state. Anything not clearly accepted or refused is unknown."""
    if status == "ok":
        return "provider_accepted"
    if status in ("rejected", "failed"):
        return "rejected"
    return "submission_unknown"


async def read(gw: Gateway, tools: Tools, call: ToolCall, deadline_mono_ms: int) -> ToolResult:
    """A read goes straight to the port — only a read (the catalog says so), without the model's attribution
    hint, under its deadline: no seal, no reservation, nothing to undo."""
    spec = gw.specs().get(call.name)
    if spec is None or spec.effect_class is not EffectClass.READ:
        return ToolResult("refused", data={"reason": "not_a_read"})
    args = {k: v for k, v in call.args.items() if k != "on"}
    budget = max(1, deadline_mono_ms - gw.clock.mono_ms())
    try:
        return await asyncio.wait_for(tools.call(call.name, args, effect_id=None, idempotency_key=None,
                                                 deadline_mono_ms=deadline_mono_ms), timeout=budget / 1000)
    except asyncio.TimeoutError:
        return ToolResult("failed", data={"reason": "timeout"})


def _mandate_alive(b, row: dict) -> bool:
    m = b.get(row["data"]["mandate"])
    if m is None or m["kind"] in (str(ItemKind.REQUEST),):
        return True
    if m["kind"] == str(ItemKind.DELEGATION):
        return m["state"] in ("active", "exhausted") and b.now < m["data"].get("expires_ms", 0)
    return m["state"] not in ("revoked",)


async def submit(gw: Gateway, tools: Tools, effect_id: str, deadline_mono_ms: int) -> ToolResult | None:
    """Submit a claimed effect. None when it did not go (held, disabled, fenced, already past `claimed`)."""
    def gate(b):
        row = b.get(effect_id)
        if row is None or row["kind"] != str(ItemKind.EFFECT):
            gw._note("refused", None, effect=effect_id, reason="no_reservation")
            b.tx.put(FLAGS, "write_disabled", {"on": True, "reason": "a call reached dispatch without a reservation",
                                               "t_ms": b.now})
            gw._note("write_disabled", None, reason="no_reservation")
            return None
        if row["state"] != "claimed":
            gw._note("refused", None, effect=effect_id, reason="not_claimed", state=row["state"])
            return None
        if (b.tx.get(FLAGS, "write_disabled") or {}).get("on"):
            gw._note("refused", None, effect=effect_id, reason="write_disabled")
            return None
        if not _mandate_alive(b, row):
            gw._note("refused", None, effect=effect_id, reason="mandate_gone")
            return None
        blocking = H.blocking(b.tx, row)
        if blocking:
            gw._note("held", None, effect=effect_id, reason="hold", holds=[h["id"] for h in blocking])
            return None
        b.move(effect_id, "submitting")
        gw._note("submitted", None, effect=effect_id, tool=row["data"]["tool"])
        return row
    row = gw._decide(gate)
    if row is None:
        return None
    budget = max(1, deadline_mono_ms - gw.clock.mono_ms())
    try:
        result = await asyncio.wait_for(tools.call(row["data"]["tool"], row["data"]["args"], effect_id=effect_id,
                                                   idempotency_key=effect_id, deadline_mono_ms=deadline_mono_ms),
                                        timeout=budget / 1000)
    except asyncio.CancelledError:
        _settle_unknown(gw, effect_id, "cancelled")        # the call may have gone: unknown, never resent
        raise
    except Exception as e:  # noqa: BLE001 — whatever the adapter raised, we do not know whether it went
        result = ToolResult("unknown", data={"error": type(e).__name__})
    to = _settled(result.status)

    def settle(b):
        b.move(effect_id, to, data={"receipt": result.receipt})
        gw._note("unknown" if to == "submission_unknown" else "receipt", None, effect=effect_id, state=to)
        if to == "provider_accepted" and (result.receipt or {}).get("delivered"):
            b.move(effect_id, "delivered")
    gw._decide(settle)
    return result


def _settle_unknown(gw: Gateway, effect_id: str, why: str) -> None:
    def fn(b):
        if (b.get(effect_id) or {}).get("state") == "submitting":
            b.move(effect_id, "submission_unknown", reason=why)
            gw._note("unknown", None, effect=effect_id, reason=why)
    gw._decide(fn)


def reconcile(gw: Gateway, effect_id: str, found: str, receipt: dict | None = None) -> None:
    """An unknown submission, settled by LOOKING at the provider (`found`: provider_accepted | rejected). A receipt
    for an effect we never reserved cuts the writes (plan §15 E5)."""
    def fn(b):
        if b.get(effect_id) is None:
            b.tx.put(FLAGS, "write_disabled", {"on": True, "reason": "a receipt without a reservation", "t_ms": b.now})
            gw._note("write_disabled", None, effect=effect_id, reason="receipt_without_reservation")
            return
        b.move(effect_id, found, data={"receipt": receipt})
        gw._note("reconciled", None, effect=effect_id, state=found)
    gw._decide(fn)


def hold(gw: Gateway, hold_id: str, endpoint: str, t_ms: int, reason: str) -> None:
    def fn(b):
        H.hold(b.tx, hold_id, endpoint, t_ms, reason)
    gw._decide(fn)


def release(gw: Gateway, effect_id: str, endpoint: str | None, gesture: bool) -> bool:
    def fn(b):
        ok = H.release(b.tx, b.get(effect_id), endpoint, gesture)
        if ok:
            gw._note("released", None, effect=effect_id, endpoint_by=endpoint)
        return ok
    return gw._decide(fn)


def recover(gw: Gateway) -> list[str]:
    """After a restart: `claimed` is provably not sent and stays; `submitting` may or may not have gone —
    `submission_unknown`, never resent (plan §15 E4)."""
    def fn(b):
        out = []
        for row in b.items(ItemKind.EFFECT, ("submitting",)):
            b.move(row["id"], "submission_unknown", reason="restart")
            gw._note("unknown", None, effect=row["id"], reason="restart")
            out.append(row["id"])
        return out
    return gw._decide(fn)

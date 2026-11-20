"""The gateway: the ONLY door from a run to the world (I8).

Three branches, by the class the host derived from the tool's declared act (`ToolSpec.effect_class`; the package keeps
no list of tools): a READ passes; a local act (WRITE) is RESERVED — `reserve` seals every intervention of the person's
in the batch and reserves ONE row per logical operation in the same transaction (I1); an effect id is a hash of
(mandate, trigger, operation), so the same operation again is the same row and a new one is never minted;
`dispatch.submit` writes it ahead before the call, an unknown outcome is reconciled by looking, never resent; a call or
a receipt without a reservation cuts every write of the account (`disable_writes`). An act that LEAVES is refused
(`held`): its owner's door is not this one yet (F2 step 4). While the person speaks, every act is refused.

Contract for the adapters (F2): the `Tools` adapter performs a real external send ONLY through the engine's one exit
door, `connectors/exit.py` (its kill switch and its inventory included). This package never sends anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from conversation.config import Config
from conversation.gateway import authority as A
from conversation.gateway import seal as S
from conversation.ledger import Book
from conversation.ports import Clock, ToolCall, ToolSpec
from conversation.telemetry import Emitter
from conversation.types import EffectClass, Ids, ItemKind

FLAGS = "flags"
OPS = "effect_ops"          # (trigger, operation) → its effect: a repeat is one read


@dataclass(frozen=True)
class Read:
    pass


@dataclass(frozen=True)
class Claimed:
    effect_id: str
    repeat: bool = False


@dataclass(frozen=True)
class Refused:
    reason: str      # unknown_tool · undeclared · held · person_speaking · unsealed · no_authority · write_disabled …


Decision = Read | Claimed | Refused


class _Abort(Exception):
    """Undo the whole transaction (a spent mandate included) and answer with this decision."""

    def __init__(self, decision: Decision) -> None:
        super().__init__(decision)
        self.decision = decision


class Gateway:
    def __init__(self, book: Book, account: str, config: Config, emitter: Emitter, clock: Clock, ids: Ids,
                 specs: Callable[[], dict[str, ToolSpec]]) -> None:
        self.book, self.account, self.cfg, self.em, self.clock, self.ids = book, account, config, emitter, clock, ids
        self.specs = specs
        self._said: list = []

    # ── telemetry, said after the transaction commits ───────────────────────────────────────────────────────────

    def _note(self, label: str, ctx: A.RunCtx | None, **payload) -> None:
        refs = {"run": ctx.run_id, "req": ctx.request_id, "endpoint": ctx.endpoint} if ctx else {}
        refs.update({k: payload.pop(k) for k in ("effect", "iv", "item", "req", "run") if k in payload})
        self._said.append((label, refs, payload))

    def _flush(self) -> None:
        said, self._said = self._said, []
        for label, refs, payload in said:
            # outside a run (a reservation's door, the writes switch) the effect is its own flow; the switch, «writes»
            trace = None if refs.get("run") or refs.get("req") else (refs.get("effect") or "writes")
            self.em.emit("conv_effect", label, owner="gateway", cause={"kind": "effect"}, refs=refs, trace=trace,
                         **payload)

    def _decide(self, fn) -> Decision:
        self._said = []
        try:
            with self.book.tx() as b:
                out = fn(b)
        except _Abort as stop:
            self._said = [s for s in self._said if s[0] == "refused"]
            self._flush()
            return stop.decision
        except BaseException:
            self._said = [s for s in self._said if s[0] in ("refused", "write_disabled")]
            self._flush()
            raise
        self._flush()
        return out

    # ── one tool call ───────────────────────────────────────────────────────────────────────────────────────────

    def request(self, ctx: A.RunCtx, call: ToolCall, *, held: bool = False) -> Decision:
        """One tool call of a run: a read passes; a local act is reserved (`Claimed`, or the reservation's refusal);
        an act that leaves is refused (`held`) — and every act while the person speaks, with that reason. The model's
        `on` is telemetry, never authority."""
        spec = self.specs().get(call.name)
        hint = call.args.get("on")
        if spec is None:
            reason = "unknown_tool"
        elif spec.effect_class is None:
            reason = "undeclared"
        elif spec.effect_class is EffectClass.READ:
            self._note("read", ctx, tool=call.name, effect_class=str(spec.effect_class), model_on=hint,
                       args={k: str(v)[:200] for k, v in call.args.items() if k != "on"})   # what was read, bounded
            self._flush()
            return Read()
        elif held:
            reason = "person_speaking"
        elif spec.effect_class is EffectClass.WRITE:
            return self.reserve(ctx, call)
        else:
            reason = "held"
        self._note("refused", ctx, tool=call.name, reason=reason, act=getattr(spec, "act", None),
                   effect_class=str(spec.effect_class) if spec else None, model_on=hint)
        self._flush()
        return Refused(reason)

    def reserve(self, ctx: A.RunCtx, call: ToolCall) -> Decision:
        """Reserve the effect of one tool call on the batch's authority floor — the seals and the row in ONE
        transaction."""
        spec = self.specs().get(call.name)
        if spec is None or spec.effect_class is EffectClass.READ:
            self._note("refused", ctx, tool=call.name, reason="not_an_effect")
            self._flush()
            return Refused("not_an_effect")
        args = {k: v for k, v in call.args.items() if k != "on"}
        return self._decide(lambda b: self._effect(b, ctx, call.name, args))

    def _refuse(self, ctx, tool: str, reason: str, **kw) -> Refused:
        self._note("refused", ctx, tool=tool, reason=reason, **kw)
        return Refused(reason)

    def _effect(self, b, ctx: A.RunCtx, tool: str, args: dict) -> Decision:
        if (b.tx.get(FLAGS, "write_disabled") or {}).get("on"):
            return self._refuse(ctx, tool, "write_disabled")
        users = A.floor(ctx)
        if not users:
            return self._refuse(ctx, tool, "no_authority")
        op = A.op_key(tool, args)
        trigger = users[0]
        existing = self._existing(b, trigger.id, op)
        if existing is not None and existing["state"] in ("rejected", "withdrawn"):
            return self._refuse(ctx, tool, f"repeat_of_{existing['state']}", effect=existing["id"])
        if existing is not None:              # the same operation on the same trigger: the SAME row
            self._note("claimed", ctx, tool=tool, effect=existing["id"], repeat=True)
            return Claimed(existing["id"], repeat=True)
        ivs = [e.refs.intervention_id for e in users]
        return self._reserve(b, ctx, trigger.id, trigger.id, op, tool, args, ivs)

    @staticmethod
    def _existing(b, trigger: str | None, op: str) -> dict | None:
        """The effect of this operation on this trigger, by its index (one read, never a scan of every effect)."""
        if trigger is None:
            return None
        ref = b.tx.get(OPS, f"{trigger}|{op}")
        return b.get(ref["effect"]) if ref else None

    def _reserve(self, b, ctx, mandate: str, trigger: str, op: str, tool: str, args: dict, ivs: list) -> Decision:
        for iv in ivs:
            if not S.seal(b.tx, iv, b.now):
                raise _Abort(self._refuse(ctx, tool, "unsealed", iv=iv))
            self._note("sealed", ctx, iv=iv)
        eid = A.effect_id(mandate, trigger, op)
        row, new = b.open_unique(ItemKind.EFFECT, eid, f"{mandate}|{trigger}|{op}", data={
            "tool": tool, "args": args, "op": op, "mandate": mandate, "trigger": trigger, "run": ctx.run_id,
            "req": ctx.request_id, "endpoint": ctx.endpoint, "ivs": ivs})
        b.tx.put(OPS, f"{trigger}|{op}", {"effect": row["id"]})
        self._note("claimed", ctx, tool=tool, effect=row["id"], mandate=mandate, repeat=not new)
        return Claimed(row["id"], repeat=not new)

    def state_of(self, effect_id: str) -> str | None:
        """Where a reserved effect stands now (a repeat of its operation is told this, never sent again)."""
        return self._decide(lambda b: (b.get(effect_id) or {}).get("state"))

    def disable_writes(self, reason: str) -> None:
        """Cut every write of the account (a leaving call reached dispatch without a valid reservation,
        or a receipt arrived for one). Reads go on."""
        def fn(b):
            b.tx.put(FLAGS, "write_disabled", {"on": True, "reason": reason, "t_ms": b.now})
            self._note("write_disabled", None, reason=reason)
        self._decide(fn)

    def seal_publication(self, ctx: A.RunCtx, ivs: list[str]) -> bool:
        """The first publication seals every intervention of the person's in the batch — all, or none and the run is
        fenced. ONE transaction."""
        def fn(b):
            for iv in ivs:
                if not S.seal(b.tx, iv, b.now):
                    raise _Abort(self._refuse(ctx, "", "unsealed", iv=iv))
                self._note("sealed", ctx, iv=iv, by="publication")
            return Read()
        return isinstance(self._decide(fn), Read)

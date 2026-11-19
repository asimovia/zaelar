"""The gateway's decisions: the ONLY place an effect is born (I8), as one reserved row per logical operation (N3).

`request` judges one tool call of a run against the run's batch (plan §15 E1): a read passes; an effect must rest on
the person's entries (the batch's authority floor) or on a mandate, seal every revision of the person's in the batch and
reserve its row — ONE transaction; an `egress` needs a delegation or a grant (spent in that same transaction), and
anything that needs a gesture (`egress` without a mandate, `destructive`, `payment`, or any effect in a batch that is
not all the person's) answers `NeedsConfirmation(handle)`. `confirm` spends a presented handle by a gesture: the control's
accounting, the spend, the seals and the reservation are ONE transaction (I1/N3). An effect id is a hash of
(mandate, trigger, operation): the same operation again returns the same row; a new one is never minted. A refused
proposal is only refused (§15 E5): the writes switch trips in `dispatch`, never here.

Contract for the adapters (F1/F2): the `Tools` adapter performs a real external send ONLY through the engine's one
exit door, `connectors/exit.py` (its kill switch and its inventory included). This package never sends anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from conversation import envelopes as E
from conversation.config import Config
from conversation.gateway import authority as A
from conversation.gateway import seal as S
from conversation.inbox.mailbox import apply_control
from conversation.ledger import Book
from conversation.ports import Clock, ToolCall, ToolSpec
from conversation.telemetry import Emitter
from conversation.types import ControlOp, EffectClass, Ids, ItemKind

FLAGS = "flags"


@dataclass(frozen=True)
class Read:
    pass


@dataclass(frozen=True)
class Claimed:
    effect_id: str
    repeat: bool = False


@dataclass(frozen=True)
class NeedsConfirmation:
    """The effect waits for a gesture on this handle (plan §15 E3)."""
    handle_id: str


@dataclass(frozen=True)
class Held:
    """A claimed effect blocked by a hold received before its submission (A7) — only that."""
    reason: str


@dataclass(frozen=True)
class Refused:
    reason: str      # unsealed · no_authority · handle_spent · handle_not_presented · not_a_gesture · write_disabled …


Decision = Read | Claimed | NeedsConfirmation | Held | Refused


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
        refs.update({k: payload.pop(k) for k in ("effect", "iv", "rev", "item") if k in payload})
        self._said.append((label, refs, payload))

    def _flush(self) -> None:
        said, self._said = self._said, []
        for label, refs, payload in said:
            self.em.emit("conv_effect", label, owner="gateway", cause={"kind": "effect"}, refs=refs, **payload)

    def _decide(self, fn, control: E.Envelope | None = None) -> Decision:
        self._said = []
        try:
            with self.book.tx() as b:
                out = fn(b)
        except _Abort as stop:
            self._said = [s for s in self._said if s[0] == "refused"]
            self._flush()
            if control is not None:                      # the control is still accounted, alone
                with self.book.tx() as b:
                    apply_control(b.tx, control.id, b.now)
            return stop.decision
        except BaseException:
            self._said = [s for s in self._said if s[0] in ("refused", "write_disabled")]
            self._flush()
            raise
        self._flush()
        return out

    # ── one tool call ───────────────────────────────────────────────────────────────────────────────────────────

    def request(self, ctx: A.RunCtx, call: ToolCall) -> Decision:
        spec = self.specs().get(call.name)
        if spec is None:
            self._note("refused", ctx, tool=call.name, reason="unknown_tool")
            self._flush()
            return Refused("unknown_tool")
        args = dict(call.args)
        hint = args.pop("on", None)                    # the model's attribution: telemetry, never authority
        if spec.effect_class is EffectClass.READ:
            self._note("read", ctx, tool=call.name, effect_class=str(spec.effect_class), model_on=hint)
            self._flush()
            return Read()
        return self._decide(lambda b: self._effect(b, ctx, spec, call.name, args, hint))

    def _refuse(self, ctx, tool: str, reason: str, **kw) -> Refused:
        self._note("refused", ctx, tool=tool, reason=reason, **kw)
        return Refused(reason)

    def _effect(self, b, ctx: A.RunCtx, spec: ToolSpec, tool: str, args: dict, hint: str | None) -> Decision:
        if (b.tx.get(FLAGS, "write_disabled") or {}).get("on"):
            return self._refuse(ctx, tool, "write_disabled")
        users = A.floor(ctx)
        op = A.op_key(tool, args)
        trigger = (users or sorted(ctx.batch.values(), key=lambda e: (e.onset_ms, e.id)) or [None])[0]
        ivs = [(e.refs.intervention_id, e.refs.revision or 1) for e in users or ()]
        if users and self.cfg.action_seal_grace_ms and not self._grace_over(b, ivs, ctx.endpoint):
            return self._refuse(ctx, tool, "seal_grace")
        if users and spec.effect_class is EffectClass.LOCAL_WRITE:
            return self._reserve(b, ctx, trigger.id, trigger.id, op, tool, args, ivs, users[0])
        mandate = A.delegation_for(b.tx, spec, args, b.now) or A.grant_for(b.tx, tool, args, b.now)
        if mandate is not None and trigger is not None:
            self._spend(b, mandate, op)
            return self._reserve(b, ctx, mandate["id"], trigger.id, op, tool, args, ivs, trigger)
        return self._issue_handle(b, ctx, spec, tool, args, op, trigger, ivs, hint)

    def _spend(self, b, mandate: dict, op: str) -> None:
        if mandate["kind"] == str(ItemKind.DELEGATION):
            used = mandate["data"].get("used", 0) + 1
            b.tx.put("items", mandate["id"], {**mandate, "data": {**mandate["data"], "used": used}})
            if used >= mandate["data"].get("max", 0):
                b.move(mandate["id"], "exhausted")
        else:
            b.move(mandate["id"], "spent", cause={"kind": "effect", "ref": op})

    def _grace_over(self, b, ivs: list, endpoint: str | None) -> bool:
        onset = (b.tx.get("onsets", endpoint or "") or {}).get("t_ms", 0)
        closed = max(((b.tx.get(S.T, iv) or {}).get("closed_ms", 0) for iv, _rev in ivs), default=0)
        return b.now - closed >= self.cfg.action_seal_grace_ms and onset <= closed

    def _reserve(self, b, ctx, mandate: str, trigger: str, op: str, tool: str, args: dict, ivs: list,
                 env: E.Envelope) -> Decision:
        for iv, rev in ivs:
            if not S.seal(b.tx, iv, rev, b.now):
                raise _Abort(self._refuse(ctx, tool, "unsealed", iv=iv, rev=rev))
            self._note("sealed", ctx, iv=iv, rev=rev)
        eid = A.effect_id(mandate, trigger, op)
        row, new = b.open_unique(ItemKind.EFFECT, eid, f"{mandate}|{trigger}|{op}", data={
            "tool": tool, "args": args, "op": op, "mandate": mandate, "trigger": trigger, "run": ctx.run_id,
            "req": ctx.request_id, "endpoint": ctx.endpoint, "ivs": ivs})
        self._note("claimed", ctx, tool=tool, effect=row["id"], authority=str(env.authority), grant=mandate,
                   repeat=not new)
        return Claimed(row["id"], repeat=not new)

    def _issue_handle(self, b, ctx, spec: ToolSpec, tool: str, args: dict, op: str, trigger, ivs: list,
                      hint: str | None) -> NeedsConfirmation:
        trig = trigger.id if trigger is not None else ctx.run_id
        hid = A.effect_id("handle", trig, op).replace("x_", "h_", 1)
        b.open(ItemKind.HANDLE, hid, data={"tool": tool, "args": args, "op": op, "trigger": trig, "ivs": ivs,
                                            **A.bound(spec, args), "run": ctx.run_id, "req": ctx.request_id,
                                            "endpoint": ctx.endpoint, "expires_ms": b.now + self.cfg.handle_ttl_ms},
               waiting_on="user")
        self._note("held", ctx, tool=tool, reason="needs_confirmation", item=hid, model_on=hint)
        return NeedsConfirmation(hid)

    def disable_writes(self, reason: str) -> None:
        """Cut every write of the account (plan §15 E5: a leaving call reached dispatch without a valid reservation,
        or a receipt arrived for one). Reads go on."""
        def fn(b):
            b.tx.put(FLAGS, "write_disabled", {"on": True, "reason": reason, "t_ms": b.now})
            self._note("write_disabled", None, reason=reason)
        self._decide(fn)

    # ── handles, delegations, grants: by id ─────────────────────────────────────────────────────────────────────

    def present(self, handle_id: str, endpoint: str | None) -> None:
        """The mouth played (or painted) the question this handle confirms: now a gesture may spend it."""
        def fn(b):
            row = b.get(handle_id)
            if row and row["state"] == "issued":
                b.move(handle_id, "presented", data={"presented_on": endpoint})
        self._decide(fn)

    def confirm(self, control: E.Envelope) -> Decision:
        """`user.control(confirm, handle_id)`: control accounted + handle spent + revisions sealed + effect reserved,
        ONE transaction. A confirmation that is not a gesture spends nothing unless a delegation covers the send."""
        body = control.body
        assert body.op is ControlOp.CONFIRM

        def fn(b):
            apply_control(b.tx, control.id, b.now)
            h = b.get(body.handle_id or "")
            d = h["data"] if h else {}
            ctx = A.RunCtx(d["run"], d["req"], {}, d["endpoint"]) if h else None
            if h is None or h["kind"] != str(ItemKind.HANDLE):
                return self._refuse(ctx, "", "handle_not_presented")
            if h["state"] == "spent":
                return self._refuse(ctx, d["tool"], "handle_spent", item=h["id"])
            if h["state"] != "presented" or b.now >= d["expires_ms"]:
                return self._refuse(ctx, d["tool"], "handle_not_presented", item=h["id"])
            spec = self.specs().get(d["tool"])
            if not body.gesture and (spec is None or A.delegation_for(b.tx, spec, d["args"], b.now) is None):
                return self._refuse(ctx, d["tool"], "not_a_gesture", item=h["id"])
            if (b.tx.get(FLAGS, "write_disabled") or {}).get("on"):
                return self._refuse(ctx, d["tool"], "write_disabled")
            b.move(h["id"], "spent", cause={"kind": "envelope", "ref": control.id})
            return self._reserve(b, ctx, h["id"], d["trigger"], d["op"], d["tool"], d["args"],
                                 [tuple(x) for x in d["ivs"]], control)
        return self._decide(fn, control)

    def decline(self, control: E.Envelope) -> None:
        def fn(b):
            apply_control(b.tx, control.id, b.now)
            h = b.get(control.body.handle_id or "")
            if h and h["state"] in ("issued", "presented"):
                b.move(h["id"], "expired", reason="declined")
        self._decide(fn)

    def delegate(self, control: E.Envelope) -> Decision:
        """A hands-free scope exists only by a gesture on the device (D8)."""
        def fn(b):
            apply_control(b.tx, control.id, b.now)
            scope = control.body.scope or {}
            if not control.body.gesture or not scope.get("recipients") or not scope.get("max"):
                return self._refuse(None, "", "not_a_gesture" if not control.body.gesture else "no_scope")
            b.open(ItemKind.DELEGATION, self.ids.new("dg"), data={**scope, "used": 0},
                   cause={"kind": "envelope", "ref": control.id})
            return Read()
        return self._decide(fn)

    def grant(self, ctx: A.RunCtx, tool: str, args: dict, expires_ms: int) -> Decision:
        """The ledger's one way to create a grant (plan §15 E6): from a batch that is ALL the person's and under an active
        delegation that covers its recipient and channel, bound to the exact operation."""
        spec = self.specs().get(tool)
        users = A.floor(ctx)

        def fn(b):
            if users is None or spec is None or A.delegation_for(b.tx, spec, args, b.now) is None:
                return self._refuse(ctx, tool, "no_authority")
            b.open(ItemKind.GRANT, self.ids.new("g"), data={"op": A.op_key(tool, args), "tool": tool, "args": args,
                                                            "expires_ms": expires_ms, "from": users[0].id},
                   cause={"kind": "envelope", "ref": users[0].id})
            return Read()
        return self._decide(fn)

    def seal_publication(self, ctx: A.RunCtx, ivs: list[tuple[str, int]]) -> bool:
        """The first publication seals every revision of the person's in the batch — all, or none (a revision was
        reopened meanwhile and the run is fenced). ONE transaction."""
        def fn(b):
            for iv, rev in ivs:
                if not S.seal(b.tx, iv, rev, b.now):
                    raise _Abort(self._refuse(ctx, "", "unsealed", iv=iv, rev=rev))
                self._note("sealed", ctx, iv=iv, rev=rev, by="publication")
            return Read()
        return isinstance(self._decide(fn), Read)

    def note_onset(self, endpoint: str, t_ms: int) -> None:
        def fn(b):
            b.tx.put("onsets", endpoint, {"t_ms": t_ms})
        self._decide(fn)

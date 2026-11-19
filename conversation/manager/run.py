"""One run: compose → model → tools through the gateway → say → close (§6.3, I9).

The batch's requests are ledger items keyed by the intervention, so a superseded run leaves them OPEN and the next
run receives them again (N1). Between two model events and between two tools is a CHECKPOINT: an interrupt set by
the policy (superseded, cancelled) takes effect there; a tool the model asked for and that did not start is skipped.
Every tool the model sees is the catalog's — ordered at most, never cut (I7). The reply is published only after its
numeric claims match their evidence (D9) and after every revision of the batch is sealed (the first publication
seals); a revision reopened meanwhile fences the run. Every request ends exactly once with its `conv_close`; the
sweep closes as `stalled` the ones that outlive the liveness budget.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation.composer import compose, view_from
from conversation.gateway import Claimed, NeedsConfirmation, Read, RunCtx, dispatch
from conversation.gateway import seal as SEAL
from conversation.inbox.mailbox import Batch
from conversation.manager import claims as CL
from conversation.manager import commands
from conversation.mouth import Device, choose
from conversation.ports import Command, Done, Failed, PromptParts, TextDelta, ToolCall, ToolResult
from conversation.types import EnvelopeKind, ItemKind, MgrState

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation, Running

REQUEST_KINDS = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT, EnvelopeKind.INTERVENTION_STATE)


def _emit(conv: "Conversation", label: str, r: "Running | None", **payload) -> None:
    refs = {"run": r.run_id, "req": r.requests[0] if r and r.requests else None,
            "endpoint": r.ctx.endpoint if r else None} if r else {}
    conv.em.emit("conv_run", label, owner="manager", cause={"kind": "batch"}, refs=refs, **payload)


def close(conv: "Conversation", req: str, to: str, label: str, **metrics) -> bool:
    """Move a request to its end and say so — at most once: the move is a compare-and-set from `open`."""
    with conv.book.tx() as b:
        row = b.get(req)
        if row is None or row["state"] != "open":
            return False
        b.move(req, to, reason=metrics.get("reason"))
        opened = row["data"].get("sealed_ms", row["created_ms"])
    conv.em.emit("conv_close", label, owner="manager", cause={"kind": "request", "ref": req}, refs={"req": req},
                 total_ms=conv.clock.now_ms() - opened, **metrics)
    return True


def sweep_liveness(conv: "Conversation", now: int) -> None:
    """I9: a request still open past the budget is closed `stalled` — counted, never left in limbo."""
    running = set(conv.current.requests) if conv.current else set()
    for _k, row in conv.book.snapshot().scan("items"):
        if (row["kind"] == str(ItemKind.REQUEST) and row["state"] == "open" and row["id"] not in running
                and now - row["created_ms"] >= conv.cfg.liveness_ms):
            close(conv, row["id"], "failed", "stalled", reason="stalled")


def _open_requests(conv: "Conversation", batch: Batch) -> tuple[str, ...]:
    reqs = []
    with conv.book.tx() as b:
        for env in batch.envelopes:
            if env.kind in REQUEST_KINDS and env.refs.intervention_id:
                rid = f"r_{env.refs.intervention_id}"
                b.open(ItemKind.REQUEST, rid, data={"req": rid, "sealed_ms": env.sealed_ms},
                       cause={"kind": "envelope", "ref": env.id})
                b.attach(rid, env.id, decided_by="id", cause={"kind": "envelope", "ref": env.id})
                reqs.append(rid)
    return tuple(dict.fromkeys(reqs))


async def run_batch(conv: "Conversation", batch: Batch) -> None:
    from conversation.manager.loop import Running
    users = [e for e in batch.envelopes if e.is_user]
    endpoint = next((e.endpoint for e in users if e.endpoint), None)
    r = Running(conv.ids.new("run"), tuple(e.id for e in batch.envelopes), _open_requests(conv, batch),
                RunCtx("", "", {e.id: e for e in batch.envelopes}, endpoint))
    r.ctx = RunCtx(r.run_id, r.requests[0] if r.requests else r.run_id, r.ctx.batch, endpoint)
    conv.current, conv.state = r, MgrState.RUNNING_UNCLAIMED
    _emit(conv, "started", r, batch_envs=list(r.batch_ids), reason=batch.reason)
    _emit(conv, "input", r, text=[getattr(e.body, "text", None) for e in batch.envelopes])
    try:
        await _steps(conv, r, batch)
    finally:
        conv.current = None
        if conv.state in (MgrState.RUNNING_CLAIMED, MgrState.RUNNING_UNCLAIMED):
            conv.state = MgrState.COLLECTING if r.interrupt == "superseded" else MgrState.IDLE


def _interrupted(conv: "Conversation", r: "Running", batch: Batch) -> bool:
    if r.interrupt is None:
        return False
    if r.interrupt == "superseded" and not r.claimed:
        conv.inbox.requeue(list(r.batch_ids))
        _emit(conv, "superseded", r)
    else:
        conv.inbox.account(list(r.batch_ids), "silent", conv.clock.now_ms())
        for req in r.requests:
            close(conv, req, "silent", "silent", reason="stopped")
        _emit(conv, "cancelled", r)
    return True


async def _steps(conv: "Conversation", r: "Running", batch: Batch) -> None:
    view = view_from(conv.store.snapshot(conv.account), prefix=conv.prefix, now_ms=conv.clock.now_ms(),
                     focus=conv.focus.of(r.ctx.endpoint), voice_endpoint=r.ctx.endpoint)
    prompt = compose(view, batch.envelopes, conv.cfg)
    tools = conv.tools.catalog()                    # the whole catalog: ordered at most, never cut (I7)
    _emit(conv, "prompt", r, prompt_chars=len(prompt.state) + len(prompt.input), tools=len(tools))
    steps: list = []
    t0 = conv.clock.mono_ms()
    for _ in range(conv.cfg.max_steps):
        called, first = False, True
        text = ""
        async for ev in conv.model.stream(PromptParts(prompt.prefix, prompt.state, prompt.conversation,
                                                      prompt.input, tuple(steps)),
                                          tools, run_id=r.run_id, model_id=conv.cfg.model_id):
            if _interrupted(conv, r, batch):
                return
            if first:
                first = False
                _emit(conv, "model_first_token", r, ttft_ms=conv.clock.mono_ms() - t0)
            if isinstance(ev, TextDelta):
                text += ev.text
            elif isinstance(ev, ToolCall):
                called = True
                steps.append((ev, await _tool(conv, r, ev)))
                if _interrupted(conv, r, batch):
                    return
            elif isinstance(ev, Command):
                _emit(conv, "command", r, command=ev.name)
                await _command(conv, r, batch, commands.parse(ev), steps)
                return
            elif isinstance(ev, Failed):
                for req in r.requests:
                    close(conv, req, "failed", "failed", reason=f"{ev.whose}:{ev.reason}")
                conv.inbox.account(list(r.batch_ids), "told", conv.clock.now_ms())
                return
            elif isinstance(ev, Done):
                _emit(conv, "model_done", r, usage=ev.usage)
        if not called:
            await _command(conv, r, batch, commands.Reply(text) if text else commands.NoReply("empty"), steps)
            return
    await _command(conv, r, batch, commands.NoReply("max_steps"), steps)


async def _tool(conv: "Conversation", r: "Running", call: ToolCall) -> ToolResult:
    t = conv.clock.mono_ms()
    decision = conv.gw.request(r.ctx, call)
    deadline = t + conv.cfg.liveness_ms
    if isinstance(decision, Read):
        result = await dispatch.read(conv.gw, conv.tools, call, deadline)
        with conv.store.tx(conv.lease) as tx:
            CL.remember(tx, result.evidence, conv.clock.now_ms(), conv.cfg.evidence_ttl_ms)
    elif isinstance(decision, Claimed):
        r.claimed, conv.state = True, MgrState.RUNNING_CLAIMED
        for env in r.ctx.batch.values():                 # the gateway sealed them: the ear must know (I3)
            if env.is_user and env.kind in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT):
                conv.sealed(env.refs.intervention_id, env.refs.revision or 1)
        if r.actions_held:
            result = ToolResult("held", data={"reason": "the person is speaking"})
        else:
            result = await dispatch.submit(conv.gw, conv.tools, decision.effect_id, deadline) or \
                ToolResult("held", data={"effect": decision.effect_id})
    elif isinstance(decision, NeedsConfirmation):
        r.presents = decision.handle_id
        result = ToolResult("needs_confirmation", data={"handle": decision.handle_id})
    else:
        result = ToolResult("refused", data={"reason": decision.reason})
    ms = conv.clock.mono_ms() - t
    if ms > conv.cfg.port_budget_ms:
        _emit(conv, "port_slow", r, port="tools", ms=ms, tool=call.name)
    return result


async def _command(conv: "Conversation", r: "Running", batch: Batch, cmd, steps: list) -> None:
    now = conv.clock.now_ms()
    if isinstance(cmd, commands.Reply):
        evidence = CL.valid(conv.store.snapshot(conv.account), now)
        bad = CL.check(list(cmd.claims), evidence)
        if bad:
            _emit(conv, "command", r, command="reply_blocked", claims=[why for _c, why in bad])
            for req in r.requests:
                close(conv, req, "silent", "silent", reason="claims_unverified")
            conv.inbox.account(list(r.batch_ids), "told", now)
            return
        if not _seal_batch(conv, r, batch):
            return
        device = conv.devices.get(r.ctx.endpoint or "", Device(r.ctx.endpoint))
        reply = choose(batch.envelopes, device)
        if reply.voice_unavailable:
            conv.speaker.voice_unavailable(r.run_id, r.ctx.endpoint)
        conv.state = MgrState.SPEAKING
        await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text=cmd.text, channels=reply.channels,
                               endpoint=r.ctx.endpoint, presents=r.presents,
                               iv=next(iter(r.ctx.batch.values())).refs.intervention_id if r.ctx.batch else None)
        for req in r.requests:
            close(conv, req, "answered", "answered", tools_ms=None, steps=len(steps))
        conv.inbox.account(list(r.batch_ids), "told", conv.clock.now_ms())
        _emit(conv, "ended", r, outcome="answered")
    else:
        for req in r.requests:
            close(conv, req, "silent", "silent", reason=getattr(cmd, "reason", None) or getattr(cmd, "name", ""))
        conv.inbox.account(list(r.batch_ids), "told", now)
        _emit(conv, "ended", r, outcome="no_reply")


class _Fenced(Exception):
    pass


def _seal_batch(conv: "Conversation", r: "Running", batch: Batch) -> bool:
    """The first publication seals every revision of the person's in the batch — all of them, or none and the run is
    fenced (a revision was reopened meanwhile: what this run would say answers a sentence that is not finished)."""
    mine = [env for env in batch.envelopes
            if env.is_user and env.kind in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)]
    try:
        with conv.store.tx(conv.lease) as tx:
            for env in mine:
                if not SEAL.seal(tx, env.refs.intervention_id, env.refs.revision or 1, conv.clock.now_ms()):
                    raise _Fenced(env.refs.intervention_id)
    except _Fenced as fence:
        _emit(conv, "fenced", r, iv=str(fence))       # a revision was reopened: nothing of this run is said
        return False
    for env in mine:
        conv.sealed(env.refs.intervention_id, env.refs.revision or 1)
    return True

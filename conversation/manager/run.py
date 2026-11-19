"""One run: compose → model → tools through the gateway → say → close (§6.3, I9).

The batch's requests were opened when their entries were accepted, keyed by the intervention, so a superseded run
leaves them OPEN and the next run receives them again (N1). Between two model events and between two tools is a
CHECKPOINT: an interrupt set by the policy or the sweep (superseded, cancelled, stalled) takes effect there; a tool
the model asked for and that did not start is skipped. Every tool the model sees is the catalog's — ordered at most,
never cut (I7). Every port call has its deadline (`conversation.guard`).

EVERY exit of a run accounts for its batch with what happened (B6, M6): answered → `told`; a deliberate silence →
`silent`; superseded → back to the queue; anything else — the provider failed or timed out, a tool raised, the
steps ran out — → `failed`, its requests closed `recovered`, and a must-tell recovery entry queued so the person
hears that it failed (worded by the model, never a fixed sentence). A numeric claim that does not match its evidence
gets ONE repair round with the reason; then the run stays silent (D9). The first publication seals the batch's
interventions; one that cannot seal fences the run.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from conversation.gateway import seal as SEAL
from conversation import envelopes as E
from conversation import guard
from conversation.composer import compose, view_from
from conversation.gateway import dispatch
from conversation.gateway.authority import RunCtx
from conversation.gateway.outbox import Claimed, Held, NeedsConfirmation, Read
from conversation.inbox.mailbox import Batch
from conversation.manager import claims as CL
from conversation.manager import commands
from conversation.mouth import Device, choose
from conversation.ports import Command, Done, Failed, PromptParts, StaleEpoch, TextDelta, ToolCall, ToolResult
from conversation.types import EnvelopeKind, ItemKind, MgrState, Surfacing

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation, Running

REQUEST_KINDS = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT, EnvelopeKind.INTERVENTION_STATE)


class _Stop(Exception):
    """End the run here with this outcome (raised at a checkpoint)."""


def _emit(conv: "Conversation", label: str, r: "Running | None", **payload) -> None:
    refs = {"run": r.run_id, "req": r.requests[0] if r and r.requests else None,
            "endpoint": r.ctx.endpoint if r else None} if r else {}
    conv.em.emit("conv_run", label, owner="manager", cause={"kind": "batch"}, refs=refs, **payload)


def close(conv: "Conversation", req: str, to: str, label: str, **metrics) -> bool:
    """Move a request to its end and say so — at most once: the move is a compare-and-set from `open`. Its
    intervention is final from then on: nothing seals it later."""
    with conv.book.tx() as b:
        row = b.get(req)
        if row is None or row["state"] != "open":
            return False
        b.move(req, to, reason=metrics.get("reason"), cause={"kind": "close", "ref": label})
        opened = row["data"].get("sealed_ms", row["created_ms"])
        iv = row["data"].get("iv")
        if iv:
            SEAL.finish(b.tx, iv, b.now)
    conv.em.emit("conv_close", label, owner="manager", cause={"kind": "request", "ref": req}, refs={"req": req},
                 total_ms=conv.clock.now_ms() - opened, **metrics)
    return True


def sweep_liveness(conv: "Conversation", now: int) -> None:
    """I9: a request still open past the budget — counted from when its batch could run (accepted complete, or
    released by a resumed voice that held it) — is closed `stalled`, the run in course too: its run is stopped at the
    next checkpoint. While a resumed voice holds the batch, the person is still speaking: no request is stalled."""
    if conv._held_iv is not None:
        return
    running = set(conv.current.requests) if conv.current else set()
    for _k, row in conv.book.snapshot().scan("items"):
        start = max(row["data"].get("sealed_ms", row["created_ms"]), conv.eligible_since)
        if (row["kind"] == str(ItemKind.REQUEST) and row["state"] == "open"
                and now - start >= conv.cfg.liveness_ms):
            if close(conv, row["id"], "failed", "stalled", reason="stalled") and row["id"] in running:
                conv.current.interrupt = "stalled"


def _requests(batch: Batch) -> tuple[str, ...]:
    return tuple(dict.fromkeys(f"r_{e.refs.intervention_id}" for e in batch.envelopes
                               if e.kind in REQUEST_KINDS and e.refs.intervention_id))


async def run_batch(conv: "Conversation", batch: Batch) -> None:
    from conversation.manager.loop import Running
    users = [e for e in batch.envelopes if e.is_user]
    endpoint = next((e.endpoint for e in users if e.endpoint), None)
    reqs = _requests(batch)
    run_id = conv.ids.new("run")
    last = max(users, key=lambda e: e.sealed_ms, default=None)
    r = Running(run_id, tuple(e.id for e in batch.envelopes), reqs,
                RunCtx(run_id, reqs[0] if reqs else run_id, {e.id: e for e in batch.envelopes}, endpoint),
                batch_seq=batch.run_seq, last_entry_ms=last.sealed_ms if last else 0,
                last_endpoint=last.endpoint if last else None)
    conv.current, conv.state = r, MgrState.RUNNING_UNCLAIMED
    _emit(conv, "started", r, batch_envs=list(r.batch_ids), reason=batch.reason)
    _emit(conv, "input", r, text=[getattr(e.body, "text", None) for e in batch.envelopes])
    try:
        await _steps(conv, r, batch)
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))   # the checkpoint already accounted the batch and said why
    except StaleEpoch:
        raise                                   # another process owns the account; its recovery takes the batch
    except asyncio.CancelledError:
        conv.inbox.requeue(list(r.batch_ids))  # the process is stopping: the batch waits for the next one
        raise
    except Exception as e:  # noqa: BLE001 — every failure of a run ends visibly; the class is recorded by name
        await _fail(conv, r, f"{type(e).__name__}")
    finally:
        conv.current = None
        if conv.state in (MgrState.RUNNING_CLAIMED, MgrState.RUNNING_UNCLAIMED):
            conv.state = MgrState.COLLECTING if r.interrupt == "superseded" else MgrState.IDLE


async def _fail(conv: "Conversation", r: "Running", reason: str) -> None:
    """The run failed: its batch is accounted `failed`, its requests close `recovered`, and the person will hear it
    — a must-tell entry the next run words (M6). What must be told is never lost to a model that stays down (NM7): it
    goes back once; failing again, the mouth says the language's last-resort line for it (the adapter words it)."""
    now = conv.clock.now_ms()
    owed = [e for e in r.ctx.batch.values() if e.must_tell and not e.is_user]
    again = [e.id for e in owed if conv.inbox.retry_once(e.id, now + conv.cfg.stall_ms, now)]
    conv.inbox.account([i for i in r.batch_ids if i not in again], "failed", now)
    if len(again) < len(owed):
        try:
            await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text="", channels=frozenset({"text"}),
                                   endpoint=r.ctx.endpoint, fallback=f"failed:{reason}")
        except guard.PortTimeout as late:
            r.said.append(("fallback", str(late)))   # the mouth is slow too: port_slow said it, the account stands
    _withdraw(conv, r, reason)
    for req in r.requests:
        if close(conv, req, "recovered", "recovered", reason=reason):
            conv.give(E.make(E.EnvelopeKind.SYSTEM_REMINDER, E.ReminderBody(f"rec-{req}", f"failed:{reason}", now),
                             producer="manager:recovery", producer_id=f"rec-{req}", account=conv.account,
                             onset_ms=now, sealed_ms=now, surfacing=Surfacing.WHEN_IDLE, must_tell=True))
    _emit(conv, "ended", r, outcome="failed", reason=reason)


def _withdraw(conv: "Conversation", r: "Running", reason: str) -> None:
    """Effects this run claimed and never submitted are withdrawn, and that is said (M5)."""
    with conv.book.tx() as b:
        for row in b.items(ItemKind.EFFECT, ("claimed",)):
            if row["data"].get("run") == r.run_id:
                b.move(row["id"], "withdrawn", reason=reason, cause={"kind": "run", "ref": r.run_id})


def _keep_held(conv: "Conversation", r: "Running", call: ToolCall) -> None:
    """An act held while the person speaks, in a run that cannot give its batch back (it already acted): it is not
    lost — a must-tell entry names it, and the next run, once the person has finished, proposes it again (NM1)."""
    now = conv.clock.now_ms()
    conv.give(E.make(E.EnvelopeKind.SYSTEM_REMINDER, E.ReminderBody(f"held-{r.run_id}-{call.call_id}",
                                                                    f"held:{call.name}", now),
                     producer="manager:held", producer_id=f"held-{r.run_id}-{call.call_id}", account=conv.account,
                     onset_ms=now, sealed_ms=now, surfacing=Surfacing.WHEN_IDLE, must_tell=True))


def resumed(conv: "Conversation", r: "Running", endpoint: str | None, t_ms: int) -> bool:
    """The person speaks again on the device of the batch's last entry, within the window of it, and the run has not
    published: the publication waits for that voice (it may be the rest of the sentence). «Not published» needs no
    flag: a run is held only at its checkpoints and at the check right before it seals, all before its line."""
    return (not r.claimed and endpoint is not None and endpoint == r.last_endpoint
            and 0 <= t_ms - r.last_entry_ms <= conv.cfg.resume_window_ms)


def _resumed_voice(conv: "Conversation", r: "Running") -> str | None:
    """The check repeated right before sealing: a voice opened after the batch's last entry, still open."""
    found = conv.ear.open_intervention(r.last_endpoint) if r.last_endpoint else None
    return found[0] if found and resumed(conv, r, r.last_endpoint, found[1]) else None


def _hold(conv: "Conversation", r: "Running", iv: str | None) -> None:
    conv.inbox.requeue(list(r.batch_ids))
    _emit(conv, "held", r, waits_for=iv)
    conv.hold_for(iv)


def _checkpoint(conv: "Conversation", r: "Running") -> None:
    if r.interrupt is None:
        return
    if r.interrupt == "resumed" and not r.claimed:
        _hold(conv, r, r.resumed_iv)               # the run stops; its batch waits for that voice
        raise _Stop()
    if r.interrupt in ("superseded", "held") and not r.claimed:
        conv.inbox.requeue(list(r.batch_ids))
        _emit(conv, "superseded", r, reason=r.interrupt)
        if r.interrupt == "held":
            conv.wait_for_voice()
        raise _Stop()
    now = conv.clock.now_ms()
    conv.inbox.account(list(r.batch_ids), "silent", now)
    _withdraw(conv, r, r.interrupt)
    for req in r.requests:
        close(conv, req, "silent", "silent", reason="stopped")
    _emit(conv, "cancelled", r, reason=r.interrupt)
    raise _Stop()


async def _steps(conv: "Conversation", r: "Running", batch: Batch) -> None:
    view = view_from(conv.store.snapshot(conv.account), prefix=conv.prefix, now_ms=conv.clock.now_ms(),
                     focus=conv.focus.of(r.ctx.endpoint), voice_endpoint=r.ctx.endpoint,
                     memory=tuple(await _memory(conv, r)))
    prompt = compose(view, batch.envelopes, conv.cfg)
    tools = conv.tools.catalog()                    # the whole catalog: ordered at most, never cut (I7)
    _emit(conv, "prompt", r, prompt_chars=len(prompt.state) + len(prompt.input), tools=len(tools))
    steps: list = []
    repaired = False
    t0 = conv.clock.mono_ms()
    refs = {"run": r.run_id}
    for _ in range(conv.cfg.max_steps):
        called, first, text = False, True, ""
        events = conv.model.stream(PromptParts(prompt.prefix, prompt.state, prompt.conversation, prompt.input,
                                               tuple(steps)), tools, run_id=r.run_id, model_id=conv.cfg.model_id)
        stream = guard.stream(conv.em, conv.cfg, events, refs)
        try:
            async for ev in stream:
                _checkpoint(conv, r)
                if first:
                    first = False
                    _emit(conv, "model_first_token", r, ttft_ms=conv.clock.mono_ms() - t0)
                if isinstance(ev, TextDelta):
                    text += ev.text
                elif isinstance(ev, ToolCall):
                    called = True
                    steps.append((ev, await _tool(conv, r, ev)))
                    _checkpoint(conv, r)
                elif isinstance(ev, Command):
                    _emit(conv, "command", r, command=ev.name)
                    if await _command(conv, r, batch, commands.parse(ev), steps, last_try=repaired):
                        return
                    repaired, called = True, True        # one repair round, with the reason as a step
                    break
                elif isinstance(ev, Failed):
                    await _fail(conv, r, f"{ev.whose}:{ev.reason}")
                    return
                elif isinstance(ev, Done):
                    _emit(conv, "model_done", r, usage=ev.usage)
        except guard.PortTimeout:
            await _fail(conv, r, "provider:timeout")
            return
        finally:                                    # a stop, a deadline, a command: the provider's stream is closed now
            await stream.aclose()                   # (review 2, MINOR 10), never left to the garbage collector
        _checkpoint(conv, r)
        if not called:
            await _command(conv, r, batch, commands.Reply(text) if text else commands.NoReply("empty"), steps,
                           last_try=True)
            return
    await _fail(conv, r, "max_steps")


async def _memory(conv: "Conversation", r: "Running") -> list:
    if conv.memory is None:
        return []
    try:
        return await guard.call(conv.em, conv.cfg, "memory",
                                conv.memory.state_blocks(conv.account, budget_tokens=800), conv.cfg.memory_ms,
                                {"run": r.run_id})
    except guard.PortTimeout as late:
        r.said.append(("memory", str(late)))  # the state goes without memory this time; port_slow said why
        return []


async def _tool(conv: "Conversation", r: "Running", call: ToolCall) -> ToolResult:
    decision = conv.gw.request(r.ctx, call, held=r.actions_held)
    deadline = conv.clock.mono_ms() + conv.cfg.tool_ms
    if isinstance(decision, Read):
        with guard.measured(conv.em, conv.cfg, "tools", {"run": r.run_id}):
            result = await dispatch.read(conv.gw, conv.tools, call, deadline)
        with conv.store.tx(conv.lease) as tx:
            CL.remember(tx, result.evidence, conv.clock.now_ms(), conv.cfg.evidence_ttl_ms)
        return result
    if isinstance(decision, Claimed):
        r.claimed, conv.state = True, MgrState.RUNNING_CLAIMED
        with guard.measured(conv.em, conv.cfg, "tools", {"run": r.run_id}):
            sent = await dispatch.submit(conv.gw, conv.tools, decision.effect_id, deadline)
        return sent or ToolResult("held", data={"effect": decision.effect_id})
    if isinstance(decision, NeedsConfirmation):
        r.presents = decision.handle_id
        return ToolResult("needs_confirmation", data={"handle": decision.handle_id})
    if isinstance(decision, Held):
        if not r.claimed:                       # the run gives its batch back and waits for that voice to end (NM1)
            r.interrupt = "held"
            _checkpoint(conv, r)
        _keep_held(conv, r, call)               # claimed: the act stays as an entry the next run proposes again
        return ToolResult("held", data={"reason": decision.reason})
    return ToolResult("refused", data={"reason": decision.reason})


async def _command(conv: "Conversation", r: "Running", batch: Batch, cmd, steps: list, *, last_try: bool) -> bool:
    """Carry out the model's order. False = repair once (a claim did not match); True = the run is over."""
    now = conv.clock.now_ms()
    if isinstance(cmd, commands.Reply):
        bad = CL.check(list(cmd.claims), CL.valid(conv.store.snapshot(conv.account), now))
        if bad:
            _emit(conv, "command", r, command="reply_blocked", claims=[why for _c, why in bad])
            if not last_try:
                steps.append((ToolCall("claims", "claims_check", {}),
                              ToolResult("refused", data={"mismatch": [why for _c, why in bad]})))
                return False
            conv.inbox.account(list(r.batch_ids), "silent", now)
            for req in r.requests:
                close(conv, req, "silent", "silent", reason="claims_unverified")
            _emit(conv, "ended", r, outcome="silent", reason="claims_unverified")
            return True
        if not _seal_batch(conv, r, batch):
            conv.inbox.requeue(list(r.batch_ids))   # fenced: the batch waits; the request stays open
            return True
        reply = choose(batch.envelopes, conv.devices.get(r.ctx.endpoint or "", Device(r.ctx.endpoint)))
        if reply.voice_unavailable:
            conv.speaker.voice_unavailable(r.run_id, r.ctx.endpoint)
        conv.state = MgrState.SPEAKING
        await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text=cmd.text, channels=reply.channels,
                               endpoint=r.ctx.endpoint, presents=r.presents,
                               iv=next(iter(r.ctx.batch.values())).refs.intervention_id if r.ctx.batch else None)
        for req in r.requests:
            close(conv, req, "answered", "answered", steps=len(steps))
        conv.inbox.account(list(r.batch_ids), "told", conv.clock.now_ms())
        _emit(conv, "ended", r, outcome="answered")
        return True
    reason = getattr(cmd, "reason", None) or getattr(cmd, "name", "")
    handed = _handed_off(conv, r)
    for req in r.requests:
        if handed:
            close(conv, req, "handed_off", "handed_off", reason="task")
        else:
            close(conv, req, "silent", "silent", reason=reason)
    conv.inbox.account(list(r.batch_ids), "silent", now)
    _emit(conv, "ended", r, outcome="handed_off" if handed else "no_reply", reason=reason)
    return True


def _handed_off(conv: "Conversation", r: "Running") -> bool:
    """The run started work that goes on without it: a tool the catalog declares as a hand-off was claimed."""
    specs = {t.name: t for t in conv.tools.catalog()}
    for _k, row in conv.book.snapshot().scan("items"):
        d = row["data"]
        if row["kind"] == str(ItemKind.EFFECT) and d.get("run") == r.run_id and \
                getattr(specs.get(d.get("tool")), "hands_off", False):
            return True
    return False


def _seal_batch(conv: "Conversation", r: "Running", batch: Batch) -> bool:
    """The first publication seals every intervention of the person's in the batch — all of them, or none and the run
    is fenced."""
    ivs = [env.refs.intervention_id for env in batch.envelopes
           if env.is_user and env.kind in (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)]
    waits = _resumed_voice(conv, r)
    if waits is not None:                          # he spoke again after the last checkpoint: hold, never publish
        _hold(conv, r, waits)
        raise _Stop()
    if not conv.gw.seal_publication(r.ctx, ivs):
        _emit(conv, "fenced", r)
        return False
    return True

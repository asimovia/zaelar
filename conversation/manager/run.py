"""One run: compose → model → tools through the gateway → say → close (§6.3, I9).

The batch's requests were opened when their entries were accepted, keyed by the intervention, so a superseded run
leaves them OPEN and the next run receives them again. Between two model events and between two tools is a
CHECKPOINT: an interrupt set by the policy or the sweep (superseded, cancelled, stalled) takes effect there; a tool
the model asked for and that did not start is skipped. Every tool the model sees is the catalog's — ordered at most,
never cut (I7). Every port call has its deadline (`conversation.guard`).

EVERY exit of a run accounts for its batch with what happened: answered → `told`; a deliberate silence →
`silent`; superseded → back to the queue; anything else — the provider failed or timed out, a tool raised, the
steps ran out — → `failed`, its requests closed `recovered`, and the person owed a line that says so (`Owed.owe`:
the host words it in the person's language; the model that failed never does). A numeric claim that does not match its evidence
gets ONE repair round with the reason; then the run stays silent. The first publication seals the batch's
interventions; one that cannot seal fences the run.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

from conversation.gateway import seal as SEAL
from conversation import envelopes as E
from conversation import guard
from conversation.composer import compose, view_from
from conversation.composer.blocks import entry_facts
from conversation.gateway import dispatch
from conversation.gateway.authority import RunCtx
from conversation.gateway.outbox import Read
from conversation.inbox.mailbox import Batch
from conversation.inbox import ordering
from conversation.manager import claims as CL
from conversation.manager import commands
from conversation.manager import record as records
from conversation.manager import stop
from conversation.mouth import Device, choose
from conversation.telemetry import root
from conversation.ports import (RELAY, UNCLAIMED, Command, Done, Failed, PromptParts, StaleEpoch, TextDelta, ToolCall,
                                ToolResult)
from conversation.composer.compose import BARGE, CONTENT, INBOX
from conversation.types import Coverage, EnvelopeKind, Evidence, ItemKind, MgrState

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation, Running

REQUEST_KINDS = (EnvelopeKind.USER_UTTERANCE, EnvelopeKind.USER_TEXT)


class _Stop(Exception):
    """End the run here with this outcome (raised at a checkpoint)."""


class _Stalled(_Stop):
    """The liveness closed the run's requests `stalled`: they still owe him a line (never silence)."""


def _emit(conv: "Conversation", label: str, r: "Running | None", **payload) -> None:
    refs = {"run": r.run_id, "req": r.requests[0] if r and r.requests else None,
            "endpoint": r.ctx.endpoint if r else None} if r else {}
    conv.em.emit("conv_run", label, owner="manager", cause={"kind": "batch"}, refs=refs, **payload)


def close(conv: "Conversation", req: str, to: str, label: str, run: "Running | None" = None, **metrics) -> bool:
    """Move a request to its end and say so — at most once: the move is a compare-and-set from `open`. Its
    intervention is final from then on: nothing seals it later. A request closed by a run carries that run, and its
    close joins that run's flow: every request of a batch, not only the first, is answered there."""
    with conv.book.tx() as b:
        row = b.get(req)
        if row is None or row["state"] != "open":
            return False
        b.move(req, to, reason=metrics.get("reason"), cause={"kind": "close", "ref": label})
        opened = row["data"].get("sealed_ms", row["created_ms"])
        iv = row["data"].get("iv")
        if iv:
            SEAL.finish(b.tx, iv, b.now)
    answered_by = {"model": run.model[0], "provider": run.model[1]} if run and run.model[0] else {}
    conv.em.emit("conv_close", label, owner="manager", cause={"kind": "request", "ref": req},
                 refs={"req": req, "run": run.run_id if run else None}, trace=run.trace if run else None,
                 total_ms=conv.clock.now_ms() - opened, **answered_by, **metrics)
    return True


def sweep_liveness(conv: "Conversation", now: int) -> None:
    """I9: a request still open past the budget is closed `stalled`, the run in course too: its run is stopped at the
    next checkpoint. The budget counts from when its batch is eligible (v3.1 §1.6): from the close of the LAST entry
    of his still in course with it — waiting for him to finish a thought said in pieces is not stalling, and each piece
    starts the budget of the batch again. A batch held for a resumed voice waits at most `resume_hold_max_ms`, well
    inside the budget, so no hold has to suspend it."""
    running = set(conv.current.requests) if conv.current else set()
    rows = [r for _k, r in conv.store.view(conv.account).scan("items", ("open",))      # a read, outside any transaction
            if r["kind"] == str(ItemKind.REQUEST)]
    if not rows:
        return
    carried, last = conv.inbox.in_course()
    for row in rows:
        start = row["data"].get("sealed_ms", row["created_ms"])
        if row["data"].get("iv") in carried and last is not None:
            start = max(start, last)
        if now - start >= conv.cfg.liveness_ms:
            mine = conv.current if row["id"] in running else None
            if close(conv, row["id"], "failed", "stalled", mine, reason="stalled"):
                if mine is not None:
                    conv.current.interrupt = "stalled"     # its run says the line, or owes it, when it stops
                elif conv.owed is not None:                # no run in course: he is owed the line
                    conv.owed.owe(conv.account, f"conv:failed:{row['id']}", "failed:stalled")


def _grace(conv: "Conversation", batch: Batch, complete: bool | None = None) -> int | None:
    """Not before: the grace of the batch's voice entries — the model's own reading when it gave one (§1.6 quater),
    the fixed graces of the marks otherwise (§1.6 ter). A batch with no voice entry has none."""
    voice = [(e.sealed_ms, e.body.terminal) for e in batch.envelopes
             if e.is_user and e.kind is EnvelopeKind.USER_UTTERANCE]
    c = conv.cfg
    return ordering.publish_at(voice, c.terminal_grace_ms, c.nonterminal_grace_ms, complete, c.complete_grace_ms,
                               c.incomplete_grace_ms)


def _zone(conv: "Conversation", now: int) -> tuple[int, str]:
    """His local zone at `now` (the `Clock` port's optional `zone`): UTC when the clock does not say."""
    return getattr(conv.clock, "zone", lambda _t: (0, "UTC"))(now)


def _open(conv: "Conversation", r: "Running") -> list[str]:
    """The run's requests still open: none, once a run has ended — answered, silent, failed or handed back."""
    mine = set(r.requests)
    return [row["id"] for _k, row in conv.store.view(conv.account).scan("items", ("open",)) if row["id"] in mine]


def _requests(batch: Batch) -> tuple[str, ...]:
    return tuple(dict.fromkeys(f"r_{e.refs.intervention_id}" for e in batch.envelopes
                               if e.kind in REQUEST_KINDS and e.refs.intervention_id))


async def run_batch(conv: "Conversation", batch: Batch) -> None:
    from conversation.manager.loop import Running
    users = [e for e in batch.envelopes if e.is_user]
    endpoint = next((e.endpoint for e in users if e.endpoint), None)
    reqs = _requests(batch)
    run_id = conv.ids.new("run")
    content = [e for e in users if e.kind in REQUEST_KINDS]
    r = Running(run_id, tuple(e.id for e in batch.envelopes), reqs,
                RunCtx(run_id, reqs[0] if reqs else run_id, {e.id: e for e in batch.envelopes}, endpoint),
                batch_seq=batch.run_seq, entries=tuple((e.sealed_ms, e.endpoint) for e in content),
                publish_at=_grace(conv, batch))
    r.trace = root({"req": reqs[0]} if reqs else {}) or run_id
    r.stages["queue_ms"] = max(0, conv.clock.now_ms() - max((e.accepted_ms for e in batch.envelopes), default=0))
    conv.em.bind(run_id, r.trace)
    conv.current, conv.state = r, MgrState.RUNNING
    _emit(conv, "started", r, batch_envs=list(r.batch_ids), reason=batch.reason)
    _emit(conv, "input", r, text=[getattr(e.body, "text", None) for e in batch.envelopes],
          entries=[{k: v for k, v in f.items() if k != "text"}
                   for f in entry_facts(batch.envelopes, _zone(conv, conv.clock.now_ms())[0])])
    try:
        if any(str(getattr(e.body, "text", "") or "").strip() for e in content) or not content:
            await _steps(conv, r, batch)
            if r.parked is None and not r.requeued and _open(conv, r):
                _emit(conv, "command", r, command="unended")    # a run never ends with his request open
                await _fail(conv, r, "unended")
        else:                                   # nothing he said reached us whole: no model, never an empty INPUT
            await _fail(conv, r, "no_words")
    except _Stalled:
        await _lost(conv, r, "stalled")         # closed by the liveness: the line is said in place, or owed
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
        if r.parked is None:                    # a reply waiting for its grace keeps the run as the one in course
            conv.current = None
            if conv.state is MgrState.RUNNING:
                conv.state = MgrState.IDLE


async def _fail(conv: "Conversation", r: "Running", reason: str) -> None:
    """The run failed: its batch is accounted `failed` and its requests close `recovered`, with the line that says so,
    worded by the host in the person's language, never by the model that just failed. A batch of typed entries is
    answered with that line in place — the mouth's text half, the request's own answer. Otherwise (his voice, or no
    line) the person is owed it — a row of the ledger of what is owed (`Owed.owe`), said when the manager is free, or
    pushed, or shown."""
    now = conv.clock.now_ms()
    conv.inbox.account(list(r.batch_ids), "failed", now)            # accounted first: whatever the mouth does next
    said, screen = False, _barge_cut(conv, r)    # a batch that cut our voice and fails says so on screen only
    try:                                    # said BEFORE the close: whoever waits on the close finds the line there
        said = await _say_failed_safely(conv, r, screen_only=screen)
    finally:                                # …and closed whatever the mouth did, a cancel included
        closed = [req for req in r.requests if close(conv, req, "recovered", "recovered", r, reason=reason)]
    if not said:                            # never silence: unsaid even on the screen, it is owed
        _owe(conv, r, reason, closed)
    _emit(conv, "ended", r, outcome="failed", reason=reason, said=said)


async def _lost(conv: "Conversation", r: "Running", reason: str) -> None:
    """A run whose requests the liveness closed: its batch accounted, and the line said in place or owed."""
    conv.inbox.account(list(r.batch_ids), "failed", conv.clock.now_ms())
    screen = _barge_cut(conv, r)
    said = await _say_failed_safely(conv, r, screen_only=screen)
    if not said:
        _owe(conv, r, reason)
    _emit(conv, "ended", r, outcome="failed", reason=reason, said=said)


def _owe(conv: "Conversation", r: "Running", reason: str, requests=None) -> None:
    if conv.owed is not None:
        for req in (r.requests if requests is None else requests):
            conv.owed.owe(conv.account, f"conv:failed:{req}", f"failed:{reason}")


async def _say_failed_safely(conv: "Conversation", r: "Running", screen_only: bool = False) -> bool:
    """`_say_failed`, and a mouth that raises is a line not said: it is owed instead, never an escape from the run."""
    try:
        return await _say_failed(conv, r, screen_only)
    except (StaleEpoch, asyncio.CancelledError):
        raise
    except Exception as e:  # noqa: BLE001 — the mouth's failure is counted; the person is owed the line
        _emit(conv, "command", r, command="mouth_failed", error=type(e).__name__)
        return False


def _line(conv: "Conversation", key: str, r: "Running") -> str:
    """The host's fixed line for `key`, in the language of what it answers (his words in the run's batch)."""
    if conv.words is None:
        return ""
    near = " ".join(str(getattr(e.body, "text", "") or "") for e in r.ctx.batch.values() if e.is_user)
    return conv.words.line(key, near=near.strip())


async def _say_failed(conv: "Conversation", r: "Running", screen_only: bool = False) -> bool:
    """The failure line as the answer to a batch of typed entries: sealed and said on the text channel. False when the
    batch holds his voice, there is no line, or the publication is fenced. `screen_only`: the batch cut our voice (a
    stop may be what he said): its line goes on the screen, whatever the batch held, and never on the voice."""
    envs = tuple(r.ctx.batch.values())
    users = [e for e in envs if e.is_user]
    line = _line(conv, "mute_lines", r)
    if not line or not users or (not screen_only and any(e.kind is not EnvelopeKind.USER_TEXT for e in users)):
        return False
    if not conv.gw.seal_publication(r.ctx, [e.refs.intervention_id for e in users]):
        _emit(conv, "fenced", r)
        return False
    reply = choose(envs, conv.devices.get(r.ctx.endpoint or "", Device(r.ctx.endpoint)), text_gets_voice=False)
    channels = frozenset({"text"}) if screen_only else reply.channels
    await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text=line, channels=channels,
                           endpoint=r.ctx.endpoint, trace=r.trace, iv=users[0].refs.intervention_id, origin=FAILURE)
    return True


def resumed(conv: "Conversation", r: "Running", iv: str, endpoint: str | None, t_ms: int) -> bool:
    """The person speaks again on a device that contributed to the batch, within the window of its last entry there —
    or even before it closed (he went on while the provider was ending) — and the run has not published: the
    publication waits for that voice (it may be the rest of the sentence), at most `resume_hold_max_ms` from the close
    of the batch's last entry. The same predicate as the inbox's (`ordering.waits_for_voice`). «Not published» needs no
    flag: a run is held only at its checkpoints, while its reply waits for its grace, and right before it seals."""
    return not r.claimed and ordering.waits_for_voice(
        list(r.entries), [(iv, t_ms, endpoint)], conv.clock.now_ms(), conv.cfg.resume_window_ms,
        conv.cfg.resume_hold_max_ms) is not None


def _resumed_voice(conv: "Conversation", r: "Running") -> tuple[str, int, str] | None:
    """The check repeated right before sealing: a voice open on a device that contributed to the batch."""
    return next(((iv, onset, ep) for iv, onset, ep in conv.ear.open_interventions()
                 if resumed(conv, r, iv, ep, onset)), None)


def _hold(conv: "Conversation", r: "Running", iv: str | None, onset: int | None = None,
          endpoint: str | None = None) -> None:
    """The run stops and its batch goes back; the inbox keeps it until that voice ends, or the hold's bound. A voice
    whose onset never reached the manager (it opened after the last checkpoint) is noted open here, so the inbox
    holds by the same rule the run did."""
    conv.inbox.requeue(list(r.batch_ids))
    if iv is not None and onset is not None:
        conv.inbox.voice_open(iv, onset, endpoint)
    _emit(conv, "held", r, waits_for=iv)


def _checkpoint(conv: "Conversation", r: "Running") -> None:
    if r.interrupt is None:
        return
    if r.interrupt == "resumed" and not r.claimed:
        _hold(conv, r, r.resumed_iv)               # the run stops; its batch waits for that voice
        raise _Stop()
    if r.interrupt == "superseded" and not r.claimed:
        conv.inbox.requeue(list(r.batch_ids))
        _emit(conv, "superseded", r, reason=r.interrupt)
        raise _Stop()
    if r.interrupt == "stalled":
        raise _Stalled()                           # its requests are closed already; what he is owed is said after
    now = conv.clock.now_ms()
    conv.inbox.account(list(r.batch_ids), "silent", now)
    for req in r.requests:
        close(conv, req, "silent", "silent", r, reason="stopped")
    _emit(conv, "cancelled", r, reason=r.interrupt)
    raise _Stop()


async def _steps(conv: "Conversation", r: "Running", batch: Batch) -> None:
    now = conv.clock.now_ms()
    offset, zone = _zone(conv, now)                 # his local time, never the host's UTC
    view = view_from(conv.store.view(conv.account), prefix=conv.prefix, now_ms=now, tz_offset_min=offset,
                     tz_name=zone, window=conv.cfg.conversation_turns,
                     voice_endpoint=r.ctx.endpoint,
                     memory=tuple(await _memory(conv, r)))
    prompt = compose(view, batch.envelopes, conv.cfg)
    tools = conv.tools.catalog()                    # the whole catalog: ordered at most, never cut (I7)
    _emit(conv, "prompt", r, prompt_chars=len(prompt.state) + len(prompt.input), tools=len(tools),
          prefix_hash=hashlib.sha256(prompt.prefix.encode()).hexdigest()[:12], prefix_chars=len(prompt.prefix),
          state=prompt.state, conversation=[{"role": t.role, "text": t.text} for t in prompt.conversation],
          input=prompt.input)               # what the model saw, but for the prefix it shares with every run
    steps: list = []
    repaired = False
    model_id = conv.cfg.model_id
    channel = "voice" if any(e.kind is EnvelopeKind.USER_UTTERANCE for e in batch.envelopes) else "text"
    t0 = conv.clock.mono_ms()
    refs = {"run": r.run_id}
    for n_step in range(conv.cfg.max_steps):
        called, first, text, dropped = False, True, "", []
        if not r.read_capped and _read_budget(conv, r, steps):     # told once why it is offered no read
            steps.append((ToolCall("reads", "reads_check", {}), ToolResult("refused", data={"reason": READS_DONE})))
        t_step = conv.clock.mono_ms()
        events = conv.model.stream(PromptParts(prompt.prefix, prompt.state, prompt.conversation, prompt.input,
                                               tuple(steps), channel), tools, run_id=r.run_id,
                                   model_id=model_id)      # the whole catalog always (I7): past the budget, refused
        stream = guard.stream(conv.em, conv.cfg, events, refs)
        try:
            async for ev in stream:
                _checkpoint(conv, r)
                if first:
                    first = False
                    _emit(conv, "model_first_token", r, ttft_ms=conv.clock.mono_ms() - t0)
                    stage = "model_first_ms" if n_step == 0 else "model_after_tool_ms"
                    r.stages[stage] = r.stages.get(stage, 0) + conv.clock.mono_ms() - t_step
                if isinstance(ev, TextDelta):
                    text += ev.text
                elif isinstance(ev, ToolCall):
                    called = True
                    over = _read_budget(conv, r, steps)        # a read past the budget is never made
                    steps.append((ev, ToolResult("refused", data={"reason": READS_DONE}) if over
                                   else await _tool(conv, r, ev)))
                    _checkpoint(conv, r)
                elif isinstance(ev, Command):
                    order = commands.parse(ev)
                    r.reading = getattr(order, "complete", r.reading)     # its last reading of his thought
                    _emit(conv, "command", r, command=ev.name, complete=getattr(order, "complete", None),
                          derived=sum(c.derived for c in getattr(order, "claims", ())),
                          unclaimed=ev.args.get(UNCLAIMED))
                    if isinstance(order, commands.Stop):
                        called = True
                        if stop.take(conv, r, order, steps) and order.scope in commands.ABANDONS:
                            await stop.stopped(conv, r)  # the run in course is abandoned: nothing more of it
                            return
                        continue                         # a stop of our voice or of what plays: the run may go on
                    r.ordered = True
                    if await _command(conv, r, batch, order, steps, last_try=repaired):
                        return
                    repaired, called = True, True        # one repair round, with the reason as a step
                    break
                elif isinstance(ev, Failed):
                    await _fail(conv, r, f"{ev.whose}:{ev.reason}")
                    return
                elif isinstance(ev, Done):
                    usage = ev.usage or {}
                    r.model = (str(usage.get("model") or ""), str(usage.get("provider") or "")) if usage.get(
                        "model") else r.model           # who answered: the titular, or its stand-in after a relay
                    _emit(conv, "model_done", r, usage=ev.usage, model=r.model[0], provider=r.model[1])
                    dropped = [d.get("name") for d in (ev.usage or {}).get("dropped", ()) if isinstance(d, dict)]
        except guard.PortTimeout:
            if first and model_id != RELAY:        # the deadline passed with nothing from the model: the same step
                model_id = RELAY                    # goes once to the stand-in — nothing said, nothing fired
                _emit(conv, "command", r, command="relay", reason="provider:timeout")
                continue
            await _fail(conv, r, "provider:timeout")
            return
        finally:                                    # a stop, a deadline, a command: the provider's stream is closed now
            await stream.aclose()                   # never left to the garbage collector
        _checkpoint(conv, r)
        if r.stopped and called and not r.ordered:  # a stop, and nothing more: the batch closes stopped, unsaid
            await stop.stopped(conv, r)
            return
        if not called:                              # no order came: text instead, or one the client could not read
            _emit(conv, "command", r, command="text_without_order" if text else "no_order", chars=len(text),
                  dropped=dropped)
            if not r.asked_for_order:               # once per run, whatever other repair it had: the order again
                r.asked_for_order, repaired = True, True
                steps.append((ToolCall("orders", "orders_check", {}),
                              ToolResult("refused", data={"reason": UNREAD if dropped else NO_ORDER})))
                continue
            if not await _say_lost(conv, r, batch, steps, "no_order"):   # never a no_reply: he is told
                await _fail(conv, r, "no_order")
            return
    if not await _say_lost(conv, r, batch, steps, "max_steps"):   # reads to the cap: he still hears something
        await _fail(conv, r, "max_steps")


async def _say_lost(conv: "Conversation", r: "Running", batch: Batch, steps: list, why: str) -> bool:
    """Never silence: the language's own «I lost that» line (`mute_lines`), counted as `why`. False with no line."""
    line = _line(conv, "mute_lines", r)
    if not line:
        return False
    _emit(conv, "command", r, command=why)
    r.origin, r.lost = FAILURE, why
    held = commands.Reply(line, complete=r.reading)    # it waits the grace the model's last reading gave the thought
    if not _park(conv, r, batch, held, line, len(steps), conv.clock.now_ms()):
        await _publish(conv, r, batch, line, len(steps))
    return True


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
        t_tool = conv.clock.mono_ms()
        with guard.measured(conv.em, conv.cfg, "tools", {"run": r.run_id}):
            result = await dispatch.read(conv.gw, conv.tools, call, deadline)
        r.stages["tools_ms"] = r.stages.get("tools_ms", 0) + conv.clock.mono_ms() - t_tool
        with conv.store.tx(conv.lease) as tx:
            CL.remember(tx, result.evidence, conv.clock.now_ms(), conv.cfg.evidence_ttl_ms)
        return result
    r.acts_refused.append(call.name)
    return ToolResult("refused", data={"reason": decision.reason})


#: a refused figure's repair: the answer again without what it cannot back — the honest line only if that fails too
RESTATE = "these figures are not in the evidence they cite: reply again without them (what was found, or a question)"
#: an order written as the reply's words, and a silence after a refused act: what the repair round says
AS_TEXT = "the text is what the person hears: the order is the call itself, never its words"
SAY_THE_ACT = "an act held or refused is a reply that says so"
EMPTY = "a reply is the words he hears: it has none"
TYPED_TO_YOU = "a line typed to you is addressed to you: reply to it"
ADDRESSED = "his words reached you as addressed to you: reply to them"
#: the source of an evidence built from his own entries
HIS_WORDS = "his_words"
NO_ORDER = "the answer is an order: reply or no_reply"
UNREAD = "your order could not be read (its arguments were not valid JSON): send it again"
SAY_WHAT_WAS_FOUND = "you read for his words: a reply says what was found, or what is missing to answer"


#: the call ids of the run's own repair steps: never a read
ORDERS_ID, CLAIMS_ID, READS_ID = "orders", "claims", "reads"
PSEUDO = frozenset({ORDERS_ID, CLAIMS_ID, READS_ID})
READS_DONE = "no more reads in this answer: reply with what you have, and say what is missing"


def _reads(steps: list) -> list[str]:
    return [c.name for c, res in steps if c.call_id not in PSEUDO and res.status != "refused"]


def _read_budget(conv: "Conversation", r: "Running", steps: list) -> bool:
    """True once the run has read `max_reads` times or for `read_wall_ms` in all: from then on every read it asks for
    is refused, with the reason to answer now (the catalog itself is never cut, I7). Counted once, by which budget
    ran out (`reads_capped`, `read_time_capped`)."""
    if r.read_capped:
        return True
    n, spent = len(_reads(steps)), r.stages.get("tools_ms", 0)
    if n >= conv.cfg.max_reads or spent >= conv.cfg.read_wall_ms:
        r.read_capped = "reads_capped" if n >= conv.cfg.max_reads else "read_time_capped"
        _emit(conv, "command", r, command=r.read_capped, reads=n, tools_ms=spent)
    return bool(r.read_capped)


def _said_something(r: "Running") -> bool:
    """His batch holds words of his (an entry, not a noise): what was read, was read for him."""
    return any(str(getattr(e.body, "text", "") or "").strip() for e in r.ctx.batch.values() if e.is_user)
#: the orders' names, as the model could write them in its text instead of calling them
ORDER_NAMES = ("reply", "no_reply", *commands.STOPS)
ORDER_TEXT = tuple(f"{n}(" for n in ORDER_NAMES) + tuple(f"<{n}" for n in ORDER_NAMES) + ("no_reply ",)


def _order_text(text: str) -> bool:
    return str(text or "").strip().casefold().startswith(ORDER_TEXT)


#: where a line we said came from (`says.origin`): the model's reply, a reply restated after a refused figure, the
#: honest line for a figure it could not confirm (and its second wording), the language's failure line — and a
#: notice, which answers nothing
REPLY, RESTATED, UNVERIFIED, FAILURE = "reply", "restated", "unverified_fact", "failure"
UNVERIFIED_ALT = "unverified_fact_alt"
LISTENING = "listening"                 # half a thought whose rest never came: «go on, I'm listening»


def _last_answer(conv: "Conversation") -> str:
    """Where our last ANSWER to a request came from ('' with none): a notice said since is not an answer."""
    for _k, row in conv.store.view(conv.account).recent("says", 8):
        if row.get("origin") != "notice" and not row.get("notice_key"):
            return str(row.get("origin") or REPLY)
    return ""


async def _command(conv: "Conversation", r: "Running", batch: Batch, cmd, steps: list, *, last_try: bool) -> bool:
    """Carry out the model's order. False = repair (a claim did not match: the answer again without it; once more when
    the honest line was our last line, so it is never said twice in a row); True = the run is over."""
    now = conv.clock.now_ms()
    if isinstance(cmd, commands.Reply) and not str(cmd.text or "").strip():
        _emit(conv, "command", r, command="empty_reply")        # an answer he would not hear: never published
        if not last_try:
            steps.append((ToolCall("orders", "orders_check", {}), ToolResult("refused", data={"reason": EMPTY})))
            return False
        if not await _say_lost(conv, r, batch, steps, "empty_reply"):
            _silent(conv, r, "empty_reply", now)
        return True
    if isinstance(cmd, commands.Reply) and _order_text(cmd.text):
        _emit(conv, "command", r, command="order_as_text")    # his line would be our protocol's words: never said
        if not last_try:
            steps.append((ToolCall("orders", "orders_check", {}), ToolResult("refused", data={"reason": AS_TEXT})))
            return False
        if not await _say_lost(conv, r, batch, steps, "order_as_text"):
            _silent(conv, r, "order_as_text", now)
        return True
    if isinstance(cmd, commands.Reply):
        this_run = frozenset(e.id for _call, res in steps for e in getattr(res, "evidence", ()))
        his = _his_words(conv, r)                   # his figures are evidence too: never ours
        evidence = {**CL.valid(conv.store.view(conv.account), now), **his}
        bad = CL.check(list(cmd.claims), evidence, this_run, conv.cfg.derived_claims_open, tuple(r.refused))
        r.refused += [c.value for c, _why in bad if not c.derived]     # refused here, never laundered as derived
        if not bad and not last_try and conv.cfg.derived_claims_repair and any(c.derived for c in cmd.claims):
            steps.append((ToolCall("claims", "claims_check", {}),       # the switch on: its one round says the basis
                          ToolResult("refused", data={"derived": "say what each derived figure rests on"})))
            return False
        valid = evidence
        if bad:
            _emit(conv, "command", r, command="reply_blocked", claims=[why for _c, why in bad],
                  detail=[CL.detail(c, why, valid.get(c.evidence_id)) for c, why in bad])
            line = _line(conv, "unverified_fact", r)
            again = bool(line) and _last_answer(conv) == UNVERIFIED  # the honest line twice in a row is never said
            if not last_try or (again and not r.restated_again):
                r.restated_again = r.restated_again or last_try
                if last_try:
                    _emit(conv, "command", r, command="restate_forced")
                steps.append((ToolCall("claims", "claims_check", {}),
                              ToolResult("refused", data={"mismatch": [why for _c, why in bad], "restate": RESTATE})))
                r.restates += 1
                return False
            if again:                               # the restate failed twice: the honest line's second wording —
                _emit(conv, "command", r, command="figures_withheld_again", claims=[why for _c, why in bad])
                alt = _line(conv, UNVERIFIED_ALT, r)    # never «say it again» for a clear question
                if not alt:
                    await _fail(conv, r, "figures_unverified_again")
                    return True
                r.origin = UNVERIFIED_ALT
                if not _park(conv, r, batch, cmd, alt, len(steps), now):
                    await _publish(conv, r, batch, alt, len(steps))
                return True
            if line:                                # never silence: the language's honest line, with no figure
                _emit(conv, "command", r, command="figures_withheld", claims=[why for _c, why in bad])
                r.origin = UNVERIFIED
                if not _park(conv, r, batch, cmd, line, len(steps), now):
                    await _publish(conv, r, batch, line, len(steps))
                return True
            conv.inbox.account(list(r.batch_ids), "silent", now)
            for req in r.requests:
                close(conv, req, "silent", "silent", r, reason="claims_unverified")
            _emit(conv, "ended", r, outcome="silent", reason="claims_unverified")
            return True
        _count_sources(conv, r, cmd.claims, this_run, his)
        if r.restates:                              # the repair worked: the answer stands without what it could not back
            _emit(conv, "command", r, command="restated", claims=len(cmd.claims), rounds=r.restates)
            r.origin = RESTATED
        if r.acts_refused:                          # an act the gateway refused, then a reply: the judge reads this one
            _emit(conv, "command", r, command="act_refused_then_reply", tools=list(r.acts_refused))
        if _park(conv, r, batch, cmd, cmd.text, len(steps), now):    # half a thought is not answered: it waits
            return True
        await _publish(conv, r, batch, cmd.text, len(steps))
        return True
    reason = getattr(cmd, "reason", None) or getattr(cmd, "name", "")
    if isinstance(cmd, commands.NoReply) and r.stopped:     # a stop, then «nothing more»: stopped, never asked again
        await stop.stopped(conv, r)
        return True
    if isinstance(cmd, commands.NoReply) and r.acts_refused and not r.asked_to_say:
        r.asked_to_say = True                   # a held or refused act is said, never a silence: asked once
        _emit(conv, "command", r, command="no_reply_after_refused_act", tools=list(r.acts_refused))
        steps.append((ToolCall("orders", "orders_check", {}),
                      ToolResult("refused", data={"refused_act": list(r.acts_refused), "reason": SAY_THE_ACT})))
        return False
    reads = _reads(steps)
    typed = _typed_only(r)
    if (isinstance(cmd, commands.NoReply) and (reads or not _barge_cut(conv, r)) and _said_something(r)
            and not r.asked_after_reads):           # it read for him, or his words reached us addressed — and then
        r.asked_after_reads = True                  # nothing: asked once. A barge-in that cut us may be silence.
        _emit(conv, "command", r, command="no_reply_after_reads" if reads else "no_reply_typed" if typed
              else "no_reply_voice", tools=reads)
        steps.append((ToolCall("orders", "orders_check", {}), ToolResult("refused", data=(
            {"read": reads, "reason": SAY_WHAT_WAS_FOUND} if reads else {"reason": TYPED_TO_YOU if typed
                                                                           else ADDRESSED}))))
        return False
    if isinstance(cmd, commands.NoReply) and cmd.complete is False and _park(conv, r, batch, cmd, None, len(steps), now):
        return True                             # «something is missing» and no reply: silent only once he did not go on
    if isinstance(cmd, commands.NoReply) and cmd.complete is False and typed:
        r.publish_at = now + conv.cfg.incomplete_grace_ms   # a typed fragment waits for its rest as a voice does
        r.parked = (None, len(steps), batch, reason)
        _emit(conv, "held", r, waits_for="grace", until_ms=r.publish_at, complete=False)
        return True
    if isinstance(cmd, commands.NoReply) and cmd.complete is False and await _listening(conv, r, batch, len(steps)):
        return True                             # its grace already over and no rest came: never nothing
    _silent(conv, r, reason, now)
    return True


def _park(conv: "Conversation", r: "Running", batch: Batch, cmd, text: str | None, steps: int, now: int) -> bool:
    """The order waits for its grace — the model's reading of the thought if it gave one, the marks' otherwise. True:
    parked (`text` None: a silent close waits)."""
    r.publish_at = _grace(conv, batch, getattr(cmd, "complete", None))
    if r.publish_at is None or now >= r.publish_at:
        return False
    r.parked = (text, steps, batch, getattr(cmd, "reason", ""))
    r.stages["parked_at"] = now
    _emit(conv, "held", r, waits_for="grace", until_ms=r.publish_at, complete=getattr(cmd, "complete", None))
    return True


def _silent(conv: "Conversation", r: "Running", reason: str, now: int) -> None:
    for req in r.requests:
        close(conv, req, "silent", "silent", r, reason=reason)
    cut = _barge_cut(conv, r)
    conv.inbox.account(list(r.batch_ids), "silent", now, reason=BARGE if cut else None)
    _emit(conv, "ended", r, outcome="no_reply", reason=reason, after_refused_act=bool(r.acts_refused),
          after_reads=r.asked_after_reads, typed_only=_typed_only(r), barge_cut=cut)


def _his_words(conv: "Conversation", r: "Running") -> dict:
    """His entries — the run's and those of the conversation window — as TEXT evidence, by intervention: the figures
    he said are his, not invented (the host reads them, `Conversation.figures`). Never our lines: what we said is no
    evidence for itself."""
    if conv.figures is None:
        return {}
    texts = {e.refs.intervention_id: str(getattr(e.body, "text", "") or "") for e in r.ctx.batch.values()
             if e.is_user and e.refs.intervention_id}
    for _k, row in conv.store.view(conv.account).recent(INBOX, 4 * conv.cfg.conversation_turns):
        body = (row.get("env") or {}).get("body") or {}
        if row.get("kind") in CONTENT and body.get("intervention_id"):
            texts.setdefault(body["intervention_id"], str(body.get("text") or ""))
    out = {}
    for iv, text in texts.items():                      # an entry with no figure in digits is evidence too: a derived
        numbers, percents = conv.figures(text)          # figure may cite what he asked, its operands read elsewhere
        out[iv] = Evidence(iv, HIS_WORDS, numbers=tuple(numbers), percents=tuple(percents))
    return out


def _count_sources(conv: "Conversation", r: "Running", claims, this_run: frozenset, his: dict) -> None:
    """A published reply's claims that rest on his words, or on a read of an earlier run still valid: counted."""
    cited = [i for c in claims for i in (c.cites or (c.evidence_id,))]
    words = sum(1 for e in cited if e in his)
    earlier = sum(1 for e in cited if e not in his and e not in this_run)
    if words:
        _emit(conv, "command", r, command="evidence_his_words", claims=words)
    if earlier:
        _emit(conv, "command", r, command="evidence_earlier_run", claims=earlier)


def _barge_cut(conv: "Conversation", r: "Running") -> bool:
    """His voice in this batch began while a line of ours sounded, and that line ended CUT — by his voice, not by our
    stop: the batch is a barge-in that stopped us."""
    voice = [e.onset_ms for e in r.ctx.batch.values() if e.is_user and e.kind is EnvelopeKind.USER_UTTERANCE]
    if not voice:
        return False
    cut = [(row["t_ms"], row.get("ended_ms") or row["t_ms"]) for _k, row in conv.store.view(conv.account).recent(
        "says", 8) if row.get("outcome") == "cut" and not row.get("stopped")]
    return any(start <= onset <= end for onset in voice for start, end in cut)


def _typed_only(r: "Running") -> bool:
    """Every entry of his in the batch was typed: a line typed to the agent is addressed to it."""
    users = [e for e in r.ctx.batch.values() if e.is_user]
    return bool(users) and all(e.kind is EnvelopeKind.USER_TEXT for e in users)


async def _publish(conv: "Conversation", r: "Running", batch: Batch, text: str, steps: int) -> None:
    """Seal, say, close the requests, account the batch."""
    if not _seal_batch(conv, r, batch):
        conv.inbox.requeue(list(r.batch_ids))   # fenced: the batch waits; the request stays open
        r.requeued = True
        return
    reply = choose(batch.envelopes, conv.devices.get(r.ctx.endpoint or "", Device(r.ctx.endpoint)),
                   text_gets_voice=bool(conv.prefs("reply_voice_to_text", True)))     # his rule, as it stands now
    if reply.voice_unavailable:
        conv.speaker.voice_unavailable(r.run_id, r.ctx.endpoint, r.trace)
    conv.state = MgrState.SPEAKING
    t_say = conv.clock.mono_ms()
    if "parked_at" in r.stages:
        r.stages["grace_wait_ms"] = max(0, conv.clock.now_ms() - r.stages.pop("parked_at"))
    await conv.speaker.say(run_id=r.run_id, request_id=r.ctx.request_id, text=text, channels=reply.channels,
                           endpoint=r.ctx.endpoint, trace=r.trace,
                           iv=next(iter(r.ctx.batch.values())).refs.intervention_id if r.ctx.batch else None,
                           origin=r.origin)
    lost = r.origin == FAILURE                  # «I lost that» said in place: told, and still a failure (as `_fail`)
    for req in r.requests:
        close(conv, req, *(("recovered", "recovered") if lost else ("answered", "answered")), r, steps=steps,
              stages={**r.stages, "publish_ms": conv.clock.mono_ms() - t_say}, **({"reason": r.lost} if lost else {}))
    conv.inbox.account(list(r.batch_ids), "told", conv.clock.now_ms())
    _emit(conv, "ended", r, outcome="failed" if lost else "answered", requests=len(r.requests),   # one close per
          **({"reason": r.lost, "said": True} if lost else {}))                                  # request, its req
    records.owe(conv, r.run_id, batch.envelopes, text)


async def _listening(conv: "Conversation", r: "Running", batch: Batch, steps: int) -> bool:
    """Half a thought, and the rest never came: never nothing — the language's «go on, I'm listening», once (never
    twice in a row, by where our last answer came from). False: no line, or it was our last answer."""
    line = _line(conv, LISTENING, r)
    if not line or _last_answer(conv) == LISTENING:
        return False
    waits = _resumed_voice(conv, r)             # his voice up again on that device: it waits for its silence
    if waits is not None:
        _hold(conv, r, *waits)
        raise _Stop()
    _emit(conv, "command", r, command=LISTENING)
    r.origin = LISTENING
    await _publish(conv, r, batch, line, steps)
    return True


def _unpark(conv: "Conversation") -> tuple:
    r = conv.current
    parked, r.parked = r.parked, None
    conv.current = None
    if conv.state is MgrState.RUNNING:
        conv.state = MgrState.IDLE
    return r, parked


def drop_parked(conv: "Conversation") -> None:
    """A reply waiting for its grace meets an interrupt — his voice again, a new entry, a stop, the liveness: it takes
    effect as at any checkpoint, and the reply is never said."""
    r = conv.current
    if r is None or r.parked is None or r.interrupt is None:
        return
    r, _parked = _unpark(conv)
    try:
        _checkpoint(conv, r)
    except _Stalled:                            # here, off any await: the line is owed, never dropped
        _owe(conv, r, "stalled")
        conv.inbox.account(list(r.batch_ids), "failed", conv.clock.now_ms())
        _emit(conv, "ended", r, outcome="failed", reason="stalled", said=False)
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))   # the checkpoint already accounted the batch and said why


async def publish_parked(conv: "Conversation") -> bool:
    """At the end of its grace a waiting reply is published. False while it still waits."""
    r = conv.current
    if r is None or r.parked is None or conv.clock.now_ms() < r.publish_at:
        return r is None or r.parked is None
    r, (text, steps, batch, reason) = _unpark(conv)
    conv.current, conv.state = r, MgrState.RUNNING          # it publishes as the run in course
    try:
        if text is None:                                    # a silent close that waited its grace looks, as a reply
            waits = _resumed_voice(conv, r)                 # does right before sealing, for his voice open again
            if waits is not None:
                _hold(conv, r, *waits)
                raise _Stop()
            if not (r.reading is False and await _listening(conv, r, batch, steps)):
                _silent(conv, r, reason, conv.clock.now_ms())
        else:
            await _publish(conv, r, batch, text, steps)
    except _Stalled:
        await _lost(conv, r, "stalled")
    except _Stop as stop:
        r.said.append(("stopped", str(stop)))   # held right before sealing: the hold already said why
    finally:
        conv.current = None
        if conv.state is MgrState.RUNNING:
            conv.state = MgrState.IDLE
    return True


def _seal_batch(conv: "Conversation", r: "Running", batch: Batch) -> bool:
    """The first publication seals every intervention of the person's in the batch — all of them, or none and the run
    is fenced."""
    ivs = [env.refs.intervention_id for env in batch.envelopes      # an incomplete one is not sealed: it asks
           if env.kind is EnvelopeKind.USER_TEXT or (env.kind is EnvelopeKind.USER_UTTERANCE
                                                    and env.body.coverage is Coverage.FULL)]
    waits = _resumed_voice(conv, r)
    if waits is not None:                          # he spoke again after the last checkpoint: hold, never publish
        _hold(conv, r, *waits)
        raise _Stop()
    if not conv.gw.seal_publication(r.ctx, ivs):
        _emit(conv, "fenced", r)
        return False
    return True

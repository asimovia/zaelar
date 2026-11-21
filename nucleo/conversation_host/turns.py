"""The turn as a unit, as the old turn's readers count it (V2-941, plan v3.2 C16): a `trace` «turno» per entry of his,
a `flow end` when its request closes, a `trace` «merge» when it is absorbed.

The Master and the viewer count a turn by its root `trace` event (its title is his words, its initiator `user`), and
call it finished by its `flow end`; an absorbed turn is folded by its `merge` marker (`observability/flows.py`). The
manager's own events keep their intervention traces; this listener only adds the old turn's units on top of them:

  · an entry of his the inbox accepted (spoken or typed) opens a turn: `voice/trace.begin` — one per intervention;
  · an entry attached to a request already open is absorbed into that request's turn (`merge`);
  · a request's close ends its turn (`flow end`, `ok` unless it failed: `recovered`, `stalled`) — except the other
    requests one run answered together, which are absorbed into the oldest one's (`merge`), never ended twice: the
    run's turn is chosen when the run STARTS, from its batch, so the order of the closes does not matter.

Our rows and the voice's `bot_speech` carry the turn's id (`corr`), so the Master never glues them to the nearest
flow by time.

The ear's own flows (one per intervention, `iv`) never stand as flows of their own (diagnosis of 2026-11-20: one order
of his left sixteen of them open next to its turns):

  · an intervention the inbox accepted is FOLDED into its turn: a `trace` «merge» marker `iv → T`, emitted directly
    (`trace.merge` orders two turns by their sequence number, and an `iv` has none), so every event of the manager
    stamped with that `iv`, before or after, reads as part of the turn;
  · an intervention the ear discarded (`no_voice`, `echo`, `no_words`…) ENDS at once: a `flow end` that carries
    `discarded` (the ear's reason). A reader counts such flows apart and never lists them as flows.
"""
from __future__ import annotations

import threading

from conversation.telemetry import CloseLabels, EarLabels

KEPT = 512
ENTRIES = frozenset({"user.utterance", "user.text"})
#: the closes that mean it failed (the package's own labels): a failed run closes its requests `recovered`
NOT_OK = frozenset({CloseLabels.RECOVERED.value, CloseLabels.FAILED.value, CloseLabels.STALLED.value})
FAILED_LINE = "conv:failed:"                              # the key of the line that tells him a request failed

_lock = threading.Lock()
_corr: dict[str, str] = {}            # intervention → its turn's trace id
_env_iv: dict[str, str] = {}          # envelope → its intervention (an attached entry is named by its envelope)
_run_first: dict[str, str] = {}       # run → its turn (the oldest of its batch's), the one its closes end
_run_steps: dict[str, list] = {}      # run → [real steps (reads and acts), tasks it opened] (R-1)
_in_course: dict[str, str] = {"run": ""}   # the run in course: its acts run in its turn's trace (`current`)
_event_trace: dict[str, str] = {}     # an event's run → the trace it opened with its origin (R-1)
#: a flow is the CONVERSATION's: its family on the viewer and the Master, never the `flow` kind's default (`worker`)
CAT = "conversation"


def _keep(d: dict, k: str, v: str) -> None:
    d[k] = v
    while len(d) > KEPT:
        d.pop(next(iter(d)))


def corr(iv: str, text: str = "") -> str:
    """The turn of intervention `iv`, opened now if it has none (`text`: his words, the turn's title)."""
    iv = str(iv or "")
    if not iv:
        return ""
    with _lock:
        tid = _corr.get(iv)
    if tid:
        return tid
    import contextvars

    from voice import trace
    tid = contextvars.copy_context().run(trace.begin, text, "turno")   # this thread's own trace stays its own
    with _lock:
        _keep(_corr, iv, tid)
    return tid


def known(iv: str) -> str:
    """The turn of `iv` if one was opened, else "" (a line owed by a notice has none)."""
    with _lock:
        return _corr.get(str(iv or ""), "")


def iv_of(req: str) -> str:
    """The intervention of a request (`r_<iv>`), or of the line that tells him it failed (`conv:failed:r_<iv>`)."""
    req = str(req or "")
    req = req[len(FAILED_LINE):] if req.startswith(FAILED_LINE) else req
    return req[2:] if req.startswith("r_") else req


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread."""
    refs = p.get("refs") or {}
    if kind == "conv_inbox" and label == "accepted" and p.get("kind") in ENTRIES and refs.get("iv"):
        with _lock:
            _keep(_env_iv, str(refs.get("env") or ""), str(refs["iv"]))
        _fold(str(refs["iv"]), corr(refs["iv"], str(p.get("text") or "")))
    elif kind == "conv_ledger" and label == "attached":
        with _lock:
            iv = _env_iv.get(str(p.get("ref") or ""), "")
        if iv and iv != iv_of(refs.get("req")):
            _merge(known(iv_of(refs.get("req"))), known(iv))
    elif kind == "conv_run" and label == "started" and refs.get("run") and p.get("origin"):
        _event_started(str(refs["run"]), str(p["origin"]))
    elif kind == "conv_run" and label == "started" and refs.get("run"):
        with _lock:
            _in_course["run"] = str(refs["run"])
            tids = [_corr.get(_env_iv.get(str(e), ""), "") for e in p.get("batch_envs") or ()]
        tids = [t for t in tids if t]
        if tids:
            from voice import trace
            with _lock:
                _keep(_run_first, str(refs["run"]), min(tids, key=trace._seq_of))
    elif kind == "conv_effect" and label in ("read", "submitted") and refs.get("run"):
        _step(str(refs["run"]), str(p.get("tool") or ""))
    elif kind == "conv_run" and label == "ended" and refs.get("run"):
        _ended(str(refs["run"]), p)
    elif kind == "conv_close":
        _closed(label, iv_of(refs.get("req")), str(refs.get("run") or ""))
    elif kind == "conv_ear" and label == EarLabels.DISCARDED.value:
        _discarded(str(p.get("trace") or ""), str(p.get("reason") or ""))


def _fold(iv: str, tid: str) -> None:
    """The intervention's flow is its turn's: the merge marker, stamped with the `iv` and naming the turn."""
    if iv and tid and iv != tid:
        from voice.observer import emit
        emit("trace", "merge", role="system", extra={"trace": iv, "merge_into": tid})


def _discarded(trace_id: str, reason: str) -> None:
    """A discarded intervention's flow ends now, saying it was a discard (never a turn of his)."""
    if trace_id:
        from voice.observer import emit
        emit("flow", "end", role="system", extra={"trace": trace_id, "ok": True, "reason": "ear_discarded",
                                                  "discarded": reason or "discarded", "cat": CAT})


def _closed(label: str, iv: str, run: str) -> None:
    tid = known(iv)
    if not tid:
        return
    with _lock:
        first = _run_first.get(run, "") if run else ""
        if run and not first:
            _keep(_run_first, run, tid)
    if first and first != tid:
        _merge(first, tid)                      # one run answered both: this turn is folded into the run's
        return
    from voice import trace
    from voice.observer import emit
    ok = label not in NOT_OK
    with _lock:
        steps, tasks = _run_steps.pop(run, [0, 0]) if run else (0, 0)
    steps += label == CloseLabels.ANSWERED.value          # it answered him: a real step too (R-1)
    with trace.scope(tid):
        emit("flow", "end", role="system", extra={"ok": ok, "reason": "turn_complete" if ok else label,
                                                  "closed": label, "cat": CAT, "steps": steps, "tasks": tasks})


def _task_acts() -> frozenset:
    from nucleo.conversation_host.declared import declared
    return frozenset(declared().get("task_acts") or ())


def _step(run: str, tool: str) -> None:
    """A read or an act the run made: a real step; an act that opens a task, a task (declared `task_acts`)."""
    with _lock:
        got = _run_steps.setdefault(run, [0, 0])
        got[0] += 1
        got[1] += tool in _task_acts()
        while len(_run_steps) > KEPT:
            _run_steps.pop(next(iter(_run_steps)))


def run_in_course() -> str:
    """The id of the run in course ("" when none): what its acts start are siblings of one execution."""
    with _lock:
        return str(_in_course["run"] or "")


def current() -> str:
    """The turn of the run in course (an event's run: its own trace), "" when none: what its acts start is the order's."""
    with _lock:
        return _run_first.get(_in_course["run"], "") or _event_trace.get(_in_course["run"], "")


def _event_started(run: str, origin: str) -> None:
    """An event's run opens a trace of its own, with its origin (a message, a cron, a cluster) and no words of his."""
    import contextvars
    tid = contextvars.copy_context().run(__import__("voice.trace", fromlist=["x"]).begin, origin, origin)
    with _lock:
        _keep(_event_trace, run, tid)
        _in_course["run"] = run


def _ended(run: str, p: dict) -> None:
    """A run ended. An event's: a flow only when it did a real step (answered); one with nothing to do is counted,
    never a flow (R-1)."""
    with _lock:
        if _in_course["run"] == run:
            _in_course["run"] = ""
        tid = _event_trace.pop(run, "")
    if not tid:
        return
    from voice import trace
    from voice.observer import emit
    did = p.get("outcome") == CloseLabels.ANSWERED.value
    with trace.scope(tid):
        emit("flow", "end", role="system", extra={"ok": p.get("outcome") != CloseLabels.FAILED.value, "cat": CAT,
                                                  "reason": "event_done" if did else "event_counted",
                                                  "origin": p.get("origin"), "steps": int(did), "tasks": 0,
                                                  **({} if did else {"discarded": str(p.get("reason") or "nothing")})})


def _merge(into: str, tid: str) -> None:
    if into and tid and into != tid:
        from voice import trace
        trace.merge(into, tid)


def _reset_for_tests() -> None:
    with _lock:
        _run_steps.clear()
        _event_trace.clear()
        _in_course["run"] = ""
        _corr.clear()
        _env_iv.clear()
        _run_first.clear()

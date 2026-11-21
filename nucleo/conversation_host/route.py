"""What the ONE decider did with each batch of his words — the `route` record (INI-078 segregation S1).

The model of the conversation decides, in its run, whether his words are conversation (A), a new task (B), words to a
task already open (C) or a change to the queue (D). Every batch it decides leaves ONE `route` event in the turn's flow
with what it saw and what it chose, so an auditor marks it right or wrong on his real sessions
(`python -m nucleo.audit.route --session <id>`):

  · `his_text` and `our_last` — what he said, and our last line before it;
  · `open` — the open-tasks block exactly as the model read it;
  · `class` — derived from the acts, through the declared table (`declared.json › route_class`): no task act is A;
  · `acts` — each act with its arguments and how it ended; `model` and `ms`.

Collected from the conversation's own telemetry and the host's ports, in the conversation's thread; never raises.
"""
from __future__ import annotations

import threading
import time

from loguru import logger

#: a batch's record, kept until its run ends (bounded: a run that never ends does not grow this)
KEPT = 64
HIS_TEXT = 600

_lock = threading.Lock()
_runs: dict[str, dict] = {}
_last_said = {"text": ""}


def _keep(run: str) -> dict:
    with _lock:
        got = _runs.setdefault(run, {"acts": [], "open": "", "his_text": "", "model": "", "t0": time.monotonic(),
                                     "our_last": _last_said["text"], "batch": []})
        while len(_runs) > KEPT:
            _runs.pop(next(iter(_runs)))
        return got


def _run_now() -> str:
    from nucleo.conversation_host import turns
    return turns.run_in_course()


def saw(title: str, text: str) -> None:
    """A state block the model read in the run in course (the open tasks), as it read it."""
    run = _run_now()
    if run and title in ("TASKS", "OPEN"):
        _keep(run)["open"] = str(text or "")


def acted(name: str, args: dict, status: str) -> None:
    """An act of the run in course, with its arguments and how it ended."""
    run = _run_now()
    if run:
        _keep(run)["acts"].append({"name": str(name), "args": dict(args or {}), "status": str(status or "")})


def ours(text: str) -> None:
    """Our line, as it is said: the next batch's `our_last`."""
    with _lock:
        _last_said["text"] = str(text or "")[:HIS_TEXT]


def class_of(acts: list[dict]) -> str:
    """A · B · C · D from the acts, by the declared table; no act of a task (or none at all) is A."""
    from nucleo.conversation_host.declared import declared
    table = declared().get("route_class") or {}
    seen = {str(a.get("name") or "") for a in acts}
    for cls in ("D", "C", "B"):                        # the queue, then an open task, then a new one
        if seen & set(table.get(cls) or ()):
            return cls
    return "A"


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread: a batch starts, its words come in, its model answers, it ends."""
    try:
        run = str((p.get("refs") or {}).get("run") or "")
        if kind != "conv_run" or not run or p.get("origin"):     # an event's run: not his words, nothing decided
            return
        if label == "started":
            _keep(run)["batch"] = list(p.get("batch_envs") or ())
        elif label == "input":
            _keep(run)["his_text"] = " ".join(str(t) for t in (p.get("text") or ()) if t)[:HIS_TEXT]
        elif label == "model_done":
            _keep(run)["model"] = str(p.get("model") or "")
        elif label == "ended":
            _ended(run, p)
    except Exception as e:  # noqa: BLE001 — a record for the auditor never decides a turn
        logger.debug(f"route: not recorded ({e!r})")


def _ended(run: str, p: dict) -> None:
    with _lock:
        rec = _runs.pop(run, None)
    if rec is None:
        return
    from nucleo.conversation_host import turns
    from voice import observer, trace
    extra = {"run": run, "batch_ids": rec["batch"], "his_text": rec["his_text"], "our_last": rec["our_last"],
             "open": rec["open"], "class": class_of(rec["acts"]), "acts": rec["acts"], "model": rec["model"],
             "ms": int((time.monotonic() - rec["t0"]) * 1000), "outcome": str(p.get("outcome") or "")}
    tid = turns._run_first.get(run, "")
    with trace.scope(tid) if tid else _nothing():
        observer.emit("route", f"route/{extra['class']}", role="system", extra=extra)


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

"""V2-877 #1 — a worker's relay brief reached the operator's chat.

The mechanism: a worker ran out of context and `relay_out_of_fuel` relaunched the errand with `context_handoff(rec)`
AS THE REQUEST. The request becomes the new record's `goal`, and the goal is
rendered everywhere the errand is shown — its title, its chat box, the live-status block, the late report — so the
instruction written for the next worker («RETOMA esta tarea… el worker anterior agotó su contexto») was shown to him.

The class: what a worker is TOLD and what the operator ASKED are two fields. The request stays his words; the brief
rides in `context["worker_brief"]`, which has exactly one reader, the worker prompt. These tests drive the relay with a
real `WorkerSession` (worker one dies of a full context, worker two answers) and read both sides of the seam.
"""
from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from nucleo.workers import relay                                     # noqa: E402
from nucleo.workers.handoff import BRIEF_KEY, context_handoff, with_worker_brief   # noqa: E402

GOAL = "Busca una guitarra zurda infantil que llegue a Soria antes del 25"
ANSWER = "Tres guitarras zurdas llegan a Soria antes del 25: la mejor es la Thomann a 89 €."
OVERFLOW = "API Error: The model has reached its context window limit."


class _Backend:
    name = "fake"

    def __init__(self, events):
        self._events = list(events)
        self.prompt = ""

    async def start(self, prompt, *, spec):
        self.prompt = prompt

    async def events(self):
        for e in self._events:
            yield e

    async def send(self, text):
        pass

    async def stop(self, *, grace=3.0):
        pass

    @property
    def alive(self):
        return True

    def native_session_id(self):
        return ""


def _ev(etype, **data):
    from nucleo.workers.base import WorkerEvent
    return WorkerEvent(task_id="1", type=etype, data=data)


@pytest.fixture
def world(monkeypatch):
    """Delivery, memory, metering and the errand door stubbed; what reaches HIM is recorded in `shown`."""
    escalations: list[tuple[str, dict]] = []
    shown: list[str] = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None, raising=False)
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain",
                        lambda req, context=None: escalations.append((req, dict(context or {}))), raising=False)

    async def _notify(title, text, **kw):
        shown.extend([str(title or ""), str(text or "")])
    monkeypatch.setattr("voice.proactive.notify", _notify, raising=False)

    async def _remember(p):
        return None
    monkeypatch.setattr("nucleo.memory_agent.remember", _remember, raising=False)
    monkeypatch.setattr("nucleo.energy.meter.report_worker_usage", lambda **kw: None, raising=False)
    return escalations, shown


def _run(rec, events, prompt="prompt"):
    from nucleo.workers.base import WorkerSpec
    from nucleo.workers.session import WorkerSession
    b = _Backend(events)
    asyncio.run(WorkerSession(b, WorkerSpec(task_id=rec.task_id), rec).run(prompt))
    return b


def _first_worker_dies(world):
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="1", goal=GOAL)
    rec.plan = ["Buscar en tiendas online", "Comprobar plazos a Soria", "Presentar"]
    rec.note = "Looking at the shipping page"
    _run(rec, [_ev("context_full", text=OVERFLOW, tokens=138492),
               _ev("result", summary=OVERFLOW, ok=False, usage={}), _ev("done")])
    escalations, _ = world
    assert len(escalations) == 1, "the blown context was not relaunched"
    return rec, escalations[0]


def _brief_lines(brief: str) -> list[str]:
    """Every piece of the brief's own prose — his goal, quoted inside it, is cut out: those words are his, not ours."""
    pieces = [bit.strip() for ln in brief.splitlines() for bit in ln.split(GOAL)]
    return [bit for bit in pieces if len(bit) > 12]


def test_the_relaunch_request_is_his_goal_and_the_brief_rides_beside_it(world):
    _, (req, ctx) = _first_worker_dies(world)
    assert req == GOAL
    assert ctx.get(BRIEF_KEY), "the fresh worker lost what was learned"
    assert not any(line in req for line in _brief_lines(ctx[BRIEF_KEY]))


def test_a_retried_errand_shows_him_his_goal_and_the_answer_and_nothing_of_the_brief(world):
    """The incident end to end: worker one dies, worker two is built the way the dispatcher's listener builds it
    (`goal=request[:200]`) and answers. Everything shown to him is checked against the brief."""
    from nucleo.workers.session import SessionRecord
    _, (req, ctx) = _first_worker_dies(world)
    rec2 = SessionRecord(task_id="2", goal=req[:200], relay_gen=int(ctx.get("relay_gen") or 0))
    b2 = _run(rec2, [_ev("result", summary=ANSWER, ok=True, usage={}), _ev("done")],
              prompt=with_worker_brief(f"OBJECTIVE: {req}", ctx))
    _, shown = world
    visible = "\n".join(shown + [rec2.goal, rec2.result_summary or "", rec2.title or ""])
    assert rec2.goal == GOAL and ANSWER in visible
    for line in _brief_lines(ctx[BRIEF_KEY]):
        assert line not in visible, f"the worker's brief reached him: {line!r}"
    assert b2.prompt.startswith(ctx[BRIEF_KEY]), "…while the WORKER does get it, first"


def test_a_stall_restart_carries_the_brief_the_same_way(world, monkeypatch):
    from nucleo.workers.session import SessionRecord
    from nucleo.circuit import ledger
    monkeypatch.setattr(relay, "restarts_left", lambda uid: True)
    monkeypatch.setattr(ledger, "get", lambda uid: {"attempts": 0})

    class _Store:
        def task_patch(self, *a, **k):
            pass
    monkeypatch.setattr(ledger, "store", lambda: _Store())
    rec = SessionRecord(task_id="1", goal=GOAL, uid="t-1")
    rec.error_class = "stalled"
    relay.restart_stalled(rec)
    escalations, _ = world
    (req, ctx), = escalations
    assert req == GOAL and ctx[BRIEF_KEY] == context_handoff(rec)


def test_the_brief_has_ONE_reader_and_it_is_the_worker_prompt():
    """The class guard: `BRIEF_KEY` may be read only where the worker's prompt is composed. Any other reader is a
    new road from the worker's instructions to something that is rendered."""
    readers = []
    for path in (ROOT / "nucleo").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if "BRIEF_KEY" not in src and '"worker_brief"' not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Name) and node.id in ("BRIEF_KEY", "_BK") or (
                    isinstance(node, ast.Constant) and node.value == "worker_brief"):
                readers.append(str(path.relative_to(ROOT)))
                break
    assert sorted(set(readers)) == ["nucleo/workers/handoff.py", "nucleo/workers/relay.py"], sorted(set(readers))

"""A turn that already holds its send task opens no second row and no worker at its close (CRIT-T2i, node 2.1756).

Measured on a live engine (2026-11-15): every send the model CALLED (the leaving act during the stream, which sets
`escalate_req["send_task"]`) emitted «a leaving act the turn could not make → its task» right after «an act that leaves
is a task». At the close, `send_task_turn.at_close` answered `""` for a turn that already held its send task, so the
close chain (`nucleo/turn/pipeline_errands.py`: `at_close` → `ask_outside_door.measure` → `ask_outside_door.claimed`)
fell through to `claimed`, which — with `screen_action` surely naming the leaving act — opened a SECOND row and a
worker for the same send (`to_message_task`). Now `at_close` answers `HELD` for that turn: truthy, so no later branch
of the chain opens anything. The chain is the product's own `if` node, compiled from `pipeline_errands.py` and run on
a real brief handle with the send doors answered; two variants (a message, ES; a calendar invite, EN).

Disarm (seen red): the `HELD` return removed from `at_close` → the chain launches a second task in both variants and
`at_close` asks `by_verdict` again — 4 reds.
"""
from __future__ import annotations

import ast
import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.request import ask_outside_door as aod, send_task_turn, send_task_words

ROOT = Path(__file__).resolve().parents[4]
VARIANTS = {
    "es-message": {"act": "mensajeria:send_to", "said": "manda un mensaje a Pablo diciendo que llego tarde",
                   "reply": "Enviado: «llego tarde» a Pablo."},
    "en-invite": {"act": "agenda:invite", "said": "invite Quinn to Friday's dinner at eight",
                  "reply": "Done — Quinn is invited to Friday's dinner."},
}


def _handle(act: str, said: str) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "judged": said, "turn_id": "t-held", "open_ids": [],
            "result": {"screen_action": {"choice": act, "confidence": 0.95},
                       "request_type": {"choice": "order", "confidence": 0.95}}}


@pytest.fixture
def world(monkeypatch):
    """Jev's door trips answered with a send in his name (so `claimed` WOULD launch), no network; every opening counted."""
    from nucleo import jev
    from nucleo.acts import errand

    def trip(said, qs, question_id=""):
        time.sleep(0.01)
        return {k: {"choice": "sends_for_him", "confidence": 0.9, "probs": {}} for k in qs if k == errand.CLASS_KEY}
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "choose_many_sync", trip)
    opened = SimpleNamespace(tasks=[], verdicts=[], workers=[])
    monkeypatch.setattr(aod, "to_message_task", lambda wid, act, said, **k: opened.tasks.append((wid, act)) or 7)
    monkeypatch.setattr(send_task_words, "by_verdict",
                        lambda brief, **k: opened.verdicts.append(k.get("model_text")) or ("", ""))
    opened.mod = SimpleNamespace(class_verdict=lambda b: None,
                                 escalate_to_slowbrain=lambda said, context=None: opened.workers.append(context) or 1)
    return opened


def _close_chain():
    """The product's close chain — the `if` whose test awaits `at_close` — as an async function of its names."""
    tree = ast.parse((ROOT / "nucleo/turn/pipeline_errands.py").read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Await)
                and getattr(n.test.value.func, "attr", "") == "at_close")
    used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    names = sorted(used - {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)})
    fn = ast.AsyncFunctionDef(name="close", args=ast.arguments(posonlyargs=[], args=[ast.arg(a) for a in names],
                              kwonlyargs=[], kw_defaults=[], defaults=[]), body=[node], decorator_list=[], returns=None,
                              type_params=[])
    mod = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope: dict = {}
    exec(compile(mod, "pipeline_errands<close chain>", "exec"), scope)   # noqa: S102 — the product's own node
    return scope["close"], names


def _run_close(world, v: dict, escalate_req: dict):
    close, names = _close_chain()
    bound = {"_send_turn": send_task_turn, "_aod": aod, "_brief": _handle(v["act"], v["said"]), "_op_text": v["said"],
             "spoken_text": v["reply"], "escalate_req": escalate_req, "worker_acted": {"v": None},
             "emit": lambda *a, **k: None, "_escalate_mod": world.mod, "_which": False}
    assert set(names) <= set(bound), f"the close chain reads names this test does not bind: {set(names) - set(bound)}"
    asyncio.run(close(**{n: bound[n] for n in names}))


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_at_close_answers_held_and_opens_nothing_for_a_turn_that_holds_its_send_task(world, variant):
    v = VARIANTS[variant]
    got = asyncio.run(send_task_turn.at_close(_handle(v["act"], v["said"]), v["said"], v["reply"],
                                              {"v": None, "send_task": True}, {"v": None}, lambda *a, **k: None,
                                              world.mod))
    assert got, "a turn that holds its send task answered falsy: the close chain falls through to `claimed`"
    assert got == send_task_turn.HELD
    assert world.verdicts == [] and world.workers == [] and world.tasks == [], "the held turn opened something"


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_the_close_chain_opens_no_second_row_for_a_held_send(world, variant):
    v = VARIANTS[variant]
    _run_close(world, v, {"v": None})          # control: the same brief with no held task — `claimed` launches
    assert world.tasks == [tuple(v["act"].split(":"))], "the control never reached `claimed`: the test proves nothing"
    world.tasks.clear()
    world.verdicts.clear()
    _run_close(world, v, {"v": None, "send_task": True})
    assert world.tasks == [], "a turn that held its send task opened a second row at its close"
    assert world.workers == [] and world.verdicts == [], "the held send was commissioned again"

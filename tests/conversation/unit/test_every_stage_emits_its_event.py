"""The observability contract (node 13.24, §8): every stage emits its event, with time, cause, owner and refs.

One request end to end — the sentence arrives, the turn closes, the inbox takes it, the run starts, the request is
opened and the sentence attached by id, the model reads and writes through the gateway, the mouth speaks and is
acknowledged, the request closes — and each stage's kind and label are seen, each carrying `t_ms`, `mono_ms`,
`cause`, `owner` and its `refs` chain. Statically: every kind and label written at a call site of the package is in
`conversation/telemetry.py`, and every kind of the contract is emitted by a piece of the architecture map.
"""
from __future__ import annotations

import ast

import pytest
import json
from pathlib import Path

from conversation.ports import Done, ToolCall
from conversation.telemetry import KINDS
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

ENGINE = Path(__file__).resolve().parents[3]
STAGES = ["conv_ear/opened", "conv_ear/closed", "conv_inbox/accepted", "conv_inbox/dequeued", "conv_run/started",
          "conv_ledger/opened", "conv_ledger/attached", "conv_run/prompt", "conv_run/model_first_token",
          "conv_effect/read", "conv_effect/refused", "conv_effect/sealed", "conv_run/command", "conv_mouth/say", "conv_mouth/started",
          "conv_mouth/ended", "conv_close/answered", "conv_inbox/accounted", "conv_run/ended"]


def test_one_request_end_to_end_says_every_stage_with_its_fields(store):
    h = Harness(store, script={"iv_000001": [
        [ToolCall("c1", "search", {"q": "w1"}), ToolCall("c2", "agenda_add", {"what": "w2"}), Done()],
        [reply("w9"), Done()]]})
    h.utter([(["w1", "w2"], 0)])
    h.pump()
    seen = h.tel.labels()
    missing = [s for s in STAGES if s not in seen]
    assert not missing, missing
    for kind, label, p in h.tel.events:
        assert isinstance(p["t_ms"], int) and isinstance(p["mono_ms"], int), (kind, label)
        assert isinstance(p["cause"], dict) and p["owner"] and isinstance(p["refs"], dict), (kind, label)
        assert label in KINDS[kind]
    by = {f"{k}/{lab}": p for k, lab, p in h.tel.events}
    assert by["conv_close/answered"]["refs"]["req"] == "r_iv_000001"
    assert by["conv_run/started"]["refs"]["run"] and by["conv_run/started"]["refs"]["req"] == "r_iv_000001"
    assert by["conv_ear/closed"]["refs"]["iv"] == "iv_000001" and by["conv_ear/closed"]["trace"] == "iv_000001"
    assert by["conv_effect/refused"]["tool"] == "agenda_add" and by["conv_effect/refused"]["reason"] == "not_a_read"
    assert by["conv_mouth/say"]["refs"]["say"]


def _call_sites() -> list[tuple[str, str, str | None]]:
    out = []
    for p in sorted((ENGINE / "conversation").rglob("*.py")):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "emit" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                label = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else None
                out.append((p.relative_to(ENGINE).as_posix(), n.args[0].value, label))
    return out


def test_every_kind_and_label_written_in_the_package_is_in_the_contract_and_on_the_map():
    sites = _call_sites()
    assert len(sites) >= 20
    bad = [s for s in sites if s[1] not in KINDS or (s[2] is not None and s[2] not in KINDS[s[1]])]
    assert not bad, bad
    m = json.loads((ENGINE / ".meshkore/docs/architecture/zaelar-architecture-map.json").read_text())
    drawn = {k for p in m["pieces"] if p["id"].startswith("c_") for k in p.get("emits", [])}
    assert set(KINDS) <= drawn, sorted(set(KINDS) - drawn)
    assert {s[1] for s in sites} == set(KINDS)


def test_a_port_call_over_its_budget_is_an_event(store):
    from conversation.config import Config
    h = Harness(store, script={"iv_000001": [[ToolCall("c1", "search", {"q": "w1"}), Done()], [reply("w2"), Done()]]},
                config=Config(port_budget_ms=5))
    h.tools.delay_s = 0.02
    h.utter([(["w1"], 0)])
    slow = [p for k, lab, p in h.tel.events if lab == "port_slow"]
    assert any(p["port"] == "tools" and p["ms"] > 5 for p in slow), slow


def test_m10_every_port_is_measured_the_store_and_the_memory_too(store):
    import asyncio
    import time

    from conversation.config import Config
    from conversation.ports import Block

    class SlowMemory:
        async def state_blocks(self, account, *, budget_tokens):
            await asyncio.sleep(0.02)
            return [Block("STATE", "w1")]

        async def screen(self, account, endpoint):
            return Block("", "")

        async def recall(self, account, query, *, k):
            return []

    h = Harness(store, script={"iv_000001": [[reply("w2"), Done()]]}, config=Config(port_budget_ms=5))
    h.conv.memory = SlowMemory()
    real_tx = h.conv.store._s.tx

    def slow_tx(lease):
        time.sleep(0.01)
        return real_tx(lease)

    h.conv.store._s.tx = slow_tx
    h.utter([(["w1"], 0)])
    ports = {p["port"] for k, lab, p in h.tel.events if lab == "port_slow"}
    assert {"memory", "store"} <= ports, ports
    assert "STATE\nw1" in h.model.calls[0].prompt.state                # memory reaches the state when it answers


def test_m9_every_event_of_a_request_carries_its_trace_and_its_cause(store):
    h = Harness(store, script={"iv_000001": [
        [ToolCall("c1", "search", {"q": "w1"}), ToolCall("c2", "agenda_add", {"what": "w2"}), Done()],
        [reply("w9"), Done()]]})
    h.utter([(["w1", "w2"], 0)])
    blank = [f"{k}/{lab}" for k, lab, p in h.tel.events if not p["trace"]]
    assert not blank, blank
    assert {p["trace"] for _k, _lab, p in h.tel.events} == {"iv_000001"}
    assert all(p["cause"].get("kind") for _k, _lab, p in h.tel.events)


def test_m9_a_run_starts_no_task_in_f1_and_an_event_needs_its_cause(store):
    from conversation.ports import Command
    from conversation.telemetry import Emitter, UnknownEvent
    h = Harness(store, script={"iv_000001": [[ToolCall("c", "task.start", {"brief": "w1"}), Done()],
                                             [Command("no_reply", {"reason": "working"}), Done()]]})
    h.utter([(["w1"], 0)])
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("silent", "working")]   # the start was refused
    with pytest.raises(UnknownEvent):
        Emitter(h.tel, h.clock, "a").emit("conv_run", "started", owner="manager")


def test_minor_11_a_telemetry_port_that_raises_does_not_stop_the_manager(store):
    class Broken:
        def emit(self, kind, label, payload):
            raise OSError("the event sink is down")

    h = Harness(store, script={"iv_000001": [[reply("w9"), Done()]]})
    h.conv.em.port = Broken()
    h.utter([(["w1"], 0)])
    assert [o.text for o in h.mouth.orders] == ["w9"] and h.conv.em.lost > 0


def test_minor10_a_run_stopped_at_a_checkpoint_closes_the_models_stream(store):
    """Review 2, MINOR 10: a stop at a checkpoint leaves the run mid-stream; the provider's stream is closed then and
    there — not left open until the garbage collector finds it."""
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from conversation.types import ControlOp
    from tests.conversation.unit.convkit import Harness
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    closed: list = []
    stop = control(ControlOp.STOP, 0, "k-stop", endpoint="d1")

    async def stream(prompt, tools, *, run_id, model_id):
        try:
            h.conv.give(stop)
            yield reply("w9")
            yield Done()
        finally:
            closed.append(h.conv.current is not None)  # closed by the run itself, while it is still the current run

    h.model.stream = stream
    h.utter([(["w1"], 0)])
    assert [lab for lab, _ in h.closes()] == ["silent"] and closed == [True]


def test_every_event_of_a_mixed_conversation_is_in_a_flow_and_every_request_joins_the_run_that_answered_it(store):
    """Round-3 finding made a property: no event outside a flow. A turn's events carry its root intervention; a run's
    (its ports, its lines) the trace it started with; a line owed its key; a stop the line it cuts; a control by id
    what it references, or itself. And a request that rode in another's batch closes WITH that run, in its flow."""
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    h.live = False
    h.typed("w1", 100)
    h.typed("w2", 200)                                       # two requests, one batch
    h.at(1000).pump()
    h.owed.add("n1", "w5")
    h.at(2000).pump()                                        # a line owed, said as it is
    h.conv.give(control(ControlOp.STOP, 2100, "k1", endpoint="d1"))
    h.conv.give(control(ControlOp.CONFIRM, 2200, "k2", endpoint="d1", gesture=True, handle="h9"))
    h.utter([(["w3"], 0)])
    h.pump()
    blank = [f"{k}/{lab}" for k, lab, p in h.tel.events if not p["trace"]]
    assert not blank, blank
    closes = [p for k, lab, p in h.tel.events if k == "conv_close"]
    started = {p["refs"]["run"]: p["trace"] for k, lab, p in h.tel.events if k == "conv_run" and lab == "started"}
    assert len(closes) == 3 and all(p["refs"].get("run") in started and p["trace"] == started[p["refs"]["run"]]
                                    for p in closes)
    first_batch = [p for p in closes if p["refs"]["req"] in ("r_iv_000001", "r_iv_000002")]
    assert {p["trace"] for p in first_batch} == {"iv_000001"}
    said = [p for k, lab, p in h.tel.events if k == "conv_mouth" and lab == "say" and p.get("notice_key")]
    assert [p["trace"] for p in said] == ["n1"]


def test_a_stop_joins_the_flow_it_stops_and_the_writes_switch_has_its_own(store):
    from conversation.gateway import dispatch
    from conversation.types import ControlOp
    from tests.conversation.unit.inboxkit import control
    import asyncio
    h = Harness(store)
    h.mouth.ack = None                                       # our line stays in course
    h.typed("w1", 100)
    h.at(1000).pump()
    line_trace = [p["trace"] for k, lab, p in h.tel.events if k == "conv_mouth" and lab == "say"][0]
    h.conv.give(control(ControlOp.STOP, 1100, "k-stop", endpoint="d1"))
    stop = [p["trace"] for k, lab, p in h.tel.events if k == "conv_inbox" and p["refs"].get("env") and
            p.get("kind") == "user.control"]
    assert stop and set(stop) == {line_trace}
    asyncio.run(dispatch.submit(h.conv.gw, h.tools, "x_never_reserved", 10 ** 9))
    off = [p["trace"] for k, lab, p in h.tel.events if k == "conv_effect" and lab in ("write_disabled", "refused")]
    assert off and all(off)

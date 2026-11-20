"""The manager's live instruments judge what they claim (node 13.53, v3.1 B7) — deterministic, with a scripted model.

The live passes (13.50 the text suite, 13.51 the `complete` bench, 13.52 the sandbox) run by request on a disposable
engine and real models. What they COMPUTE is checked here: the suite's judge goes red on a request closed twice or
never, on a forbidden route where the case exists for it, on an act, on another owner of the turn — and stays green
on a route the model chose elsewhere (a rate there, not a gate); the suite runs end to end over the manager in this
process; the bench reads the order's `complete`, counts a missing field against, and its gate goes red on a model
that always says «finished»; the sandbox boots with the switch on, every write held, the language, and Rowan.
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from conversation.ports import Command, Done, ToolCall
from tests.conversation.benchmarks import complete_bench as cb
from tests.conversation.e2e import sandbox, text_suite


def _rec(case: str, *, closes=("answered",), reply="Vale.", calls=(), refused=(), proof_ok=True, tasks=(),
         turn=None) -> dict:
    conv = next(c for c in text_suite.load([case], ["es"]))
    t = copy.deepcopy(turn or conv["turns"][0])
    ans = [{"piece": 0, "reply": reply, "tool_calls": list(calls), "refused_calls": list(refused),
            "conv": {"close": c}} for c in closes]
    proof = {"passes": proof_ok, "counters": {"manager_runs": 1, "effects_outside_read": 0}}
    return {"id": conv["id"], "case": case, "class": case, "lang": "es", "thoughts": [{"turn": t, "answers": ans}],
            "new_tasks": list(tasks), "proof": proof}


def test_the_suites_judge_is_green_on_a_good_run_and_red_on_each_broken_one():
    agenda = [{"name": "read_widget", "args": {"widget": "agenda"}}]
    assert text_suite.judge(_rec("T3", calls=agenda))["pass"]
    assert not text_suite.judge(_rec("T3", calls=[{"name": "web_search", "args": {}}] + agenda))["pass"]  # forbidden
    assert not text_suite.judge(_rec("T3", calls=agenda, closes=("answered", "answered")))["pass"]       # twice
    assert not text_suite.judge(_rec("T3", calls=agenda, closes=("no_close_yet",)))["pass"]              # never
    assert not text_suite.judge(_rec("T3", calls=agenda, proof_ok=False))["pass"]                        # another owner
    assert not text_suite.judge(_rec("T7", calls=[{"name": "read_widget", "args": {"widget": "mensajeria"}}]))["pass"]
    assert not text_suite.judge(_rec("T7", tasks=[{"id": "t1"}]))["pass"]                                # a task left
    assert text_suite.judge(_rec("T1", calls=[]))["pass"]              # T1's route is the model's: a rate, not a gate


def test_a_thought_with_nothing_to_answer_may_close_silent():
    assert text_suite.judge(_rec("T12", closes=("silent",), reply=""))["pass"]
    assert not text_suite.judge(_rec("T3", closes=("silent",), reply=""))["pass"]


class _InProcess:
    """The text channel of a manager running in this process, with a scripted model: the suite's driver as is."""

    def __init__(self):
        from nucleo.conversation_host import boot, entry, proof
        self._entry, self._proof, self._acct = entry, proof, boot.account()

    def say(self, text, session):
        return asyncio.run(self._entry.typed_and_wait(text, dev=f"text:{session}"))

    def tasks(self):
        return []

    def cancel(self, task_id):
        return None

    def flow(self, trace):
        return []

    def _req(self, method, path, body=None, timeout=30):
        return self._proof.report(self._acct)


@pytest.fixture
def manager(monkeypatch):
    from config import settings
    from nucleo.conversation_host import model, sessions, switch
    monkeypatch.setenv(switch.ENV, "1")
    monkeypatch.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    monkeypatch.setattr(settings, "_read", lambda: {})
    script = {"events": [Command("reply", {"text": "Vale."}), Done()]}

    class _Model:
        def __init__(self, *a, **k):
            pass

        async def stream(self, prompt, tools, *, run_id, model_id):
            for ev in script["events"]:
                yield ev

    monkeypatch.setattr(model, "FastModel", _Model)
    sessions.close_all()
    yield script
    sessions.close_all()


def test_the_suite_runs_end_to_end_over_the_manager(manager, tmp_path):
    convs = text_suite.load(["T12"], ["es"])
    s = asyncio.run(text_suite.run(_InProcess(), convs, 1, tmp_path))
    assert s["pass"], s
    manager["events"] = [ToolCall("c1", "send_message", {"to": "Rowan"}), Command("reply", {"text": "No puedo."}),
                         Done()]
    s = asyncio.run(text_suite.run(_InProcess(), text_suite.load(["T7"], ["es"]), 1, tmp_path))
    rec = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])
    assert s["pass"] and rec["thoughts"][0]["answers"][0]["refused_calls"]          # refused by the gateway


class _Reads:
    """A model whose order carries `complete` as scripted per item; `first_read` makes it ask a read first."""

    def __init__(self, answer, first_read=False):
        self.answer, self.first_read = answer, first_read

    async def stream(self, prompt, tools, *, run_id, model_id):
        if self.first_read and not prompt.steps:
            yield ToolCall("c1", "web_search", {"query": "w"})
            yield Done()
            return
        args = {"text": "w"}
        v = self.answer(prompt.input)
        if v is not None:
            args["complete"] = v
        yield Command("reply", args)
        yield Done()


def test_the_bench_reads_the_orders_field_and_a_missing_one_counts_against():
    assert asyncio.run(cb.read(_Reads(lambda i: False), "w", "es")) is False
    assert asyncio.run(cb.read(_Reads(lambda i: True), "w", "es")) is True
    assert asyncio.run(cb.read(_Reads(lambda i: None), "w", "es")) is None
    assert "LANGUAGE: each reply" in cb.prompt("w", "es").prefix and "«w»" in cb.prompt("w", "es").input


def test_a_provider_that_never_answers_is_infra_never_a_silent_fail():
    from conversation.ports import Failed

    class _Down:
        async def stream(self, prompt, tools, *, run_id, model_id):
            assert tools == []                                           # no read offered: it measures the field
            yield Failed("HTTP 401", "provider")

    got = asyncio.run(cb.read(_Down(), "w", "es"))
    assert got.startswith("failed:")
    s = cb.score([{"lang": "es", "label": "incomplete", "complete": got}] * 10
                 + [{"lang": "es", "label": "complete", "complete": got}] * 100)
    assert s["infra"] and not s["pass"]


def test_a_reply_that_is_an_orders_text_is_no_answer():
    rec = _rec("T12", reply='no_reply(reason="w0")')
    assert not text_suite.judge(rec)["pass"]
    assert text_suite.judge(_rec("T12", reply="Vale."))["pass"]


def _results(complete_for_incomplete, complete_for_complete) -> list[dict]:
    return ([{"lang": "es", "label": "incomplete", "complete": complete_for_incomplete} for _ in range(10)]
            + [{"lang": "es", "label": "complete", "complete": complete_for_complete} for _ in range(100)])


def test_the_benchs_gate_is_the_designs():
    assert cb.score(_results(False, True))["pass"]
    assert not cb.score(_results(True, True))["pass"]                   # always «finished»: the incomplete gate fails
    assert not cb.score(_results(False, None))["pass"]                   # no field: counts against
    mixed = _results(False, True)
    for r in mixed[:5]:
        r["complete"] = True                                             # 5 of 10 incomplete read right: under 6
    assert not cb.score(mixed)["pass"]


def test_the_bench_takes_its_items_from_the_frozen_corpus():
    it = cb.items("es", 10, 100)
    inc = [i for i in it if i["label"] == "incomplete"]
    assert len(inc) == 10 and len(it) == 110 and all(i["cut"] in ("marked", "unmarked") for i in inc)
    assert any(i["cut"] == "marked" for i in inc)


def test_the_sandbox_boots_with_the_switch_on_every_write_held_the_language_and_rowan(tmp_path):
    seen = {}

    class _Eng:
        base_url = "http://127.0.0.1:43999"

    def spawn(*, workspace, port, extra_env, boot_timeout):
        seen["env"] = extra_env
        return _Eng()

    class _Client:
        def __init__(self, port):
            seen["port"] = port

        def seed(self, lang):
            seen["lang"] = lang
            return ["Rowan"]

    eng, seeded = sandbox.boot("es", workspace=Path(tmp_path), port=43999, spawn=spawn, client=_Client)
    assert seen["env"] == {"ZAELAR_CONVERSATION": "1", "ZAELAR_HOLD_OUTBOUND": "all", "ZAELAR_LANGUAGE": "es",
                           "ZAELAR_CONVERSATION_SANDBOX": "1"}
    assert json.loads((Path(tmp_path) / "config" / "v2.json").read_text()) == {"privacy": {"obfuscate": False}}
    assert seen["port"] == 43999 and seen["lang"] == "es" and seeded == ["Rowan"]

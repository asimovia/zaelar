"""What the first live smoke of the manager found, held (node 13.54, v3.1 B7b).

  · a figure that still matches nothing after the one repair is never silence: the language's own line is said, with
    no figure, and counted (`figures_withheld`);
  · text the model writes with no order is never said — not even one that looks like an order: one round asks for an
    order, then the request closes silent (`no_order`), counted (`text_without_order`);
  · an entry reaches the model with its id, channel and time — facts, never our protocol's «closed»;
  · each close says where its time went (queue, model, tools, grace, publish), and each port is slow by its own budget;
  · a disposable engine resets its conversation between two isolated cases — and a real engine refuses to;
  · the verdict that no act left counts no seal: a reply's seal is no act.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from conversation.config import Config
from conversation.ports import Done, TextDelta, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from conversation.types import Evidence
from nucleo.conversation_host.figures import figures
from tests.conversation.unit.convkit import Harness

TEXT = Evidence("ev_t1", "search", numbers=figures("cerró a 186,52"))


class _Words:
    def __init__(self, line):
        self._line = line

    def line(self, key):
        return self._line if key == "unverified_fact" else ""


def _rounds(h, rounds):
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]


def test_a_figure_that_still_matches_nothing_is_never_silence(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words("w_line")
    bad = [{"entity": "", "period": "", "metric": "", "direction": "", "value": 17, "evidence_id": "ev_t1"}]
    _rounds(h, [[ToolCall("c1", "market_data", {}), Done()], [reply("w9 17", bad), Done()]])
    h.tools.answers["market_data"] = ToolResult("ok", {}, (TEXT,))
    h.utter([(["w1"], 0)])
    assert [o.text for o in h.mouth.orders] == ["w_line"]                     # the honest line, never the 17
    assert [lab for lab, _ in h.closes()] == ["answered"]
    assert any(p.get("command") == "figures_withheld" for k, lab, p in h.tel.events if k == "conv_run")


def test_with_no_line_in_the_pack_it_stays_silent_as_before(store):
    h = Harness(store, grace=False)
    bad = [{"entity": "", "period": "", "metric": "", "direction": "", "value": 17, "evidence_id": "ev_none"}]
    _rounds(h, [[reply("w9 17", bad), Done()]])
    h.utter([(["w1"], 0)])
    assert h.mouth.orders == [] and [lab for lab, _ in h.closes()] == ["silent"]


@pytest.mark.parametrize("text", ["w9 here is your answer", 'no_reply(reason="w0")'])
def test_text_with_no_order_is_never_said(store, text):
    h = Harness(store, grace=False)
    _rounds(h, [[TextDelta(text), Done()]])
    h.utter([(["w1"], 0)])
    assert h.mouth.orders == [] and [lab for lab, _ in h.closes()] == ["silent"]
    assert len(h.model.calls) == 2                                            # one round asked for an order
    assert [p.get("command") for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"] == \
        ["text_without_order", "text_without_order"]


def test_text_then_an_order_in_the_repair_is_answered(store):
    h = Harness(store, grace=False)
    _rounds(h, [[TextDelta("w8"), Done()], [reply("w9"), Done()]])
    h.utter([(["w1"], 0)])
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_an_entry_reaches_the_model_with_facts_never_our_protocols_words(store):
    h = Harness(store, grace=False)
    h.utter([(["w1"], 0)])
    line = h.model.calls[-1].prompt.input.splitlines()[1]
    assert " · voice · " in line and "closed" not in line and "incomplete" not in line


def test_each_close_says_where_its_time_went(store):
    h = Harness(store, grace=True)
    _rounds(h, [[ToolCall("c1", "market_data", {}), Done()], [reply("w9"), Done()]])
    closed = h.utter([(["w1"], 0)], terminal=True)
    h.at(closed + h.conv.cfg.terminal_grace_ms + 100).pump()
    stages = next(p["stages"] for k, lab, p in h.tel.events if k == "conv_close" and lab == "answered")
    assert {"queue_ms", "model_first_ms", "tools_ms", "model_after_tool_ms", "grace_wait_ms", "publish_ms"} <= set(stages)
    assert stages["grace_wait_ms"] > 0


def test_each_port_is_slow_by_its_own_budget():
    from conversation import guard
    from conversation.testing.fakes import ListTelemetry
    from conversation.telemetry import Emitter

    class _Clock:
        def now_ms(self):
            return 0

        def mono_ms(self):
            return 0

    tel = ListTelemetry()
    em = Emitter(tel, _Clock(), "a")
    cfg = Config()
    guard._slow(em, cfg, "store", 60)                                          # a transaction at 60 ms: slow
    guard._slow(em, cfg, "model", 400)                                         # a model's first event at 0.4 s: not
    assert [p["port"] for k, lab, p in tel.events if lab == "port_slow"] == ["store"]


def test_a_real_engine_refuses_the_reset_a_sandbox_allows(monkeypatch, tmp_path):
    from memory.db import Database
    from memory.api import conv
    from server import voice_api
    monkeypatch.delenv("ZAELAR_CONVERSATION_SANDBOX", raising=False)
    got = asyncio.run(voice_api.debug_conversation_reset())
    assert got.status_code == 403
    db = Database(tmp_path / "z.db")
    try:
        with db.cursor() as cur:
            cur.execute("INSERT INTO conv_rows (account, tbl, key, state, updated_ms, row) VALUES "
                        "('a','inbox','e1','accounted',0,'{}'), ('b','inbox','e1','accounted',0,'{}')")
        assert conv.wipe("a", db=db) == 1
        assert [r[0] for r in db.query("SELECT account FROM conv_rows")] == ["b"]      # the other account untouched
    finally:
        db.close()


def test_the_verdict_that_no_act_left_counts_no_seal():
    from tests.conversation.tools import verdicts
    rec = {"events": [("conv_effect", "sealed", {})], "exits": {}, "tasks_new": [], "drafts_new": []}
    assert verdicts.r6_no_effects(rec).status == verdicts.PASS
    rec["events"].append(("conv_effect", "claimed", {"tool": "send_message"}))
    assert verdicts.r6_no_effects(rec).status == verdicts.FAIL


def test_the_provider_is_told_every_answer_is_an_order():
    from conversation.ports import PromptParts
    from nucleo.conversation_host.model import FastModel
    seen = {}

    class _Client:
        async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role, **kw):
            seen.update(kw)
            if False:
                yield ""

    async def go():
        return [ev async for ev in FastModel(_Client(), spec="s").stream(PromptParts("p", "", (), "i"), [],
                                                                          run_id="r", model_id="")]
    asyncio.run(go())
    assert seen.get("tool_choice") == "required"

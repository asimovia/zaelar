"""A run reads within its budget, then answers with what it has (node 13.107, V2-941, v3.1 B7l — the flagship case's
23–36 s: three searches about 9 s apart).

A run reads at most `max_reads` times (genome threshold, 2), and for at most `read_wall_ms` in all (12 s). Past either
budget every read it asks for is refused with the reason to answer now — what it found, and what is missing — and the
run is told so once; the catalog itself is never cut (I7). Counted once, by which budget ran out: `reads_capped`,
`read_time_capped`. A read already in flight is never cut.

The STEP budget (`max_steps`) behaves the same (INI-078, the operator's test of 2026-11-21 17:17: searches that
count as acts spent the six steps and the run ended «I did part of it… shall I carry on?»): on the run's last step
every call is refused with the reason to answer now, and the model replies with what it found — the run never ends
on `lost_after_acts` while the model still answers. Disarm: drop the last step's refusal in `run._steps`.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.manager import run as R
from conversation.ports import Done, ToolCall
from conversation.testing.fakes import FixedWords
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


def _searching(h):
    """A model that keeps asking for one more search until a read is refused, then answers."""
    def step(ids):
        last = h.model.calls[-1].prompt.steps
        if any(res.status == "refused" for _c, res in last):
            return [reply("w9"), Done()]
        return [ToolCall(f"c{len(h.model.calls)}", "market_data", {"q": "w1"}), Done()]
    h.model.default = step


def _commands(h):
    return [(p.get("command"), p.get("reads")) for k, lab, p in h.tel.events if k == "conv_run" and lab == "command"
            and p.get("command") in ("reads_capped", "read_time_capped")]


def test_past_two_reads_the_run_answers_with_what_it_has(store):
    h = Harness(store, grace=False)
    _searching(h)
    h.typed("w1", 0)
    h.settle(2000)
    assert [c[0] for c in h.tools.calls] == ["market_data", "market_data"]          # never a third
    assert _commands(h) == [("reads_capped", 2)] and [o.text for o in h.mouth.orders] == ["w9"]
    told = [res.data.get("reason") for c, res in h.model.calls[-1].prompt.steps if c.call_id == R.READS_ID]
    assert told == [R.READS_DONE]
    assert all(len(c.tools) == len(h.model.calls[0].tools) for c in h.model.calls)  # the catalog is never cut (I7)


def test_past_its_time_the_run_answers_even_under_the_count(store):
    h = Harness(store, grace=False, config=Config(max_reads=5))
    _searching(h)
    h.tools.before = lambda name: h.clock.advance(7000)                              # each search takes 7 s
    h.typed("w1", 0)
    h.settle(60_000)
    assert len(h.tools.calls) == 2 and _commands(h) == [("read_time_capped", 2)]
    assert [o.text for o in h.mouth.orders] == ["w9"]


def test_a_read_past_the_budget_in_the_same_step_is_refused_not_made(store):
    h = Harness(store, grace=False)
    calls = [ToolCall(f"c{i}", "market_data", {"q": f"w{i}"}) for i in range(3)]
    h.model.default = lambda ids: [*calls, Done()] if len(h.model.calls) == 1 else [reply("w9"), Done()]
    h.typed("w1", 0)
    h.settle(2000)
    assert len(h.tools.calls) == 2
    refused = [res.data.get("reason") for c, res in h.model.calls[-1].prompt.steps if res.status == "refused"]
    assert R.READS_DONE in refused and [o.text for o in h.mouth.orders] == ["w9"]


def test_the_budgets_are_the_genomes_thresholds():
    from nucleo.conversation_host import config
    import json
    genesis = json.load(open("nucleo/genesis.json"))
    cfg, problems = config.build(genesis)
    assert problems == [] and (cfg.max_reads, cfg.read_wall_ms, cfg.evidence_ttl_ms) == (2, 12_000, 30 * 60_000)
    assert cfg.evidence_ttl_ms == cfg.session_gap_ms                                 # evidence lives one session
    from nucleo.conversation_host import guards
    guards.configure(cfg)                                                            # what the boot hands the guards
    assert cfg.reclaim_tail_ms == 3000 and guards._cfg["reclaim_tail_ms"] == 3000


def test_a_run_that_spends_its_steps_ends_with_the_models_answer(store):
    """Acts (not reads) until the last step: there every call is refused with the reason, and the model answers."""
    h = Harness(store, grace=False, config=Config(max_steps=3))
    h.conv.words = FixedWords()

    def step(ids):
        told = any(c.call_id == R.STEPS_ID for c, _res in h.model.calls[-1].prompt.steps)
        return [reply("w9"), Done()] if told else [ToolCall(f"c{len(h.model.calls)}", "agenda_add", {"q": f"w{len(h.model.calls)}"}), Done()]
    h.model.default = step
    h.typed("w1", 0)
    h.settle(3000)
    assert [o.text for o in h.mouth.orders] == ["w9"], "the run ends with the model's answer, never «part was done»"
    assert len(h.tools.calls) == 2, "the last step makes no call"
    told = [res.data.get("reason") for c, res in h.model.calls[-1].prompt.steps if c.call_id == R.STEPS_ID]
    assert told == [R.STEPS_DONE]


def test_a_call_on_the_last_step_is_refused_with_the_reason(store):
    h = Harness(store, grace=False, config=Config(max_steps=2))
    h.conv.words = FixedWords()
    h.model.default = lambda ids: [ToolCall(f"c{len(h.model.calls)}", "agenda_add", {"q": f"w{len(h.model.calls)}"}), Done()]
    h.typed("w1", 0)
    h.settle(3000)
    assert len(h.tools.calls) == 1, "the call of the last step is never made"

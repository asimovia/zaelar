"""A typed line waits for nothing, and a reply is sized by its channel (node 13.96, V2-941, v3.1 B7i).

The corpus measured a fixed ~500 ms that every typed close paid (the collect window), against real gaps between his
lines of p10 3.8 s: the window is a genome threshold now, 0 by default — a burst is handled by a newer line superseding
the run. Replies grew from p50 135 to 236 characters: the prefix declares each channel's length as DATA (genesis
`conversation.reply_budget`, its LENGTH line), and the host gives each channel a generous ceiling on what the model
writes (`max_tokens`), never a cutting one. The prompt carries its batch's channel: voice when it holds his voice.
"""
from __future__ import annotations

import asyncio

from conversation.config import Config
from conversation.ports import Done, PromptParts
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import config, model, prefix
from tests.conversation.unit.convkit import Harness


def test_the_collect_window_is_a_genome_threshold_at_zero():
    import genome
    assert Config().collect_ms == 0
    assert genome.genesis()["conversation"]["thresholds"]["collect_ms"] == 0
    cfg, problems = config.build()
    assert cfg.collect_ms == 0 and problems == []
    bad = genome.genesis()
    bad = {**bad, "conversation": {**bad["conversation"],
                                   "thresholds": {**bad["conversation"]["thresholds"], "collect_ms": 99_999}}}
    assert any("collect_ms" in p for p in config.build(bad)[1])                # out of its declared bounds: refused


def test_a_typed_line_runs_at_once(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.typed("w1", 100)
    assert len(h.model.calls) == 1 and h.model.calls[0].prompt.channel == "text"   # no window to wait out


def test_the_prompt_carries_its_batchs_channel(store):
    h = Harness(store, grace=False)
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.utter([(["w1"], 0)])
    assert h.model.calls[0].prompt.channel == "voice"


def test_the_prefix_declares_each_channels_length_as_data():
    import genome
    from nucleo.conversation_host import tools_read
    from nucleo.llm.fast_client import est_tokens
    budget = {"voice": "w1 w2", "text": "w3"}
    line = prefix.build([], native="English", name="English", budget=budget).splitlines()[-1]
    assert line == "LENGTH: text: w3; voice: w1 w2; longer only when asked"
    real = prefix.build(tools_read.catalog(), native="English", name="English", agent="Johnny", person="Quinn",
                        held=prefix.held_acts(), budget=genome.genesis()["conversation"]["reply_budget"])
    assert est_tokens(len(real)) <= prefix.MAX_TOKENS


class _Client:
    def __init__(self):
        self.seen = []

    async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role, **kw):
        self.seen.append(kw.get("max_tokens"))
        on_tool_call("reply", {"text": "w1", "claims": []})
        if False:
            yield ""


def test_each_channel_gets_its_generous_ceiling():
    import genome
    ceilings = genome.genesis()["conversation"]["max_tokens"]
    client = _Client()

    async def go(channel):
        return [ev async for ev in model.FastModel(client, spec="s").stream(
            PromptParts("w0", "", (), "w1", (), channel), [], run_id="r1", model_id="")]
    asyncio.run(go("voice"))
    asyncio.run(go("text"))
    asyncio.run(go(""))
    assert client.seen == [ceilings["voice"], ceilings["text"], None] and ceilings["voice"] < ceilings["text"]

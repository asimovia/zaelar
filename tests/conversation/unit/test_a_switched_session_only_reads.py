"""A switched session only reads (node 13.41, v3.1 B4).

The catalogue is five reads — the world (search), a widget, his memory, the agent itself, the catalogue — and every
class is DERIVED: a tool with a type of the event vocabulary is that type's (leaving, or a local write), one with no
type is a read only when all it declares is reading. The search door gets the model's proposal and no judge, so the
turn's classifier is never asked; recall leaves no reinforcement; a door that fails is a `failed` result the model
sees; a call to anything else is refused by the gateway. Which provider answered — after a relay too — reaches the
run's `model_done`.
"""
from __future__ import annotations

import asyncio

from conversation.ports import Done, ToolResult
from conversation.types import EffectClass
from nucleo.conversation_host import tools_read
from nucleo.conversation_host.model import DONE_KEYS, FastModel
from search.result import SearchResult, Source


def _call(tools, name, args):
    return asyncio.run(tools.call(name, args, effect_id=None, idempotency_key=None, deadline_mono_ms=10 ** 12))


def test_the_catalogue_is_five_reads_and_every_class_is_derived():
    cat = tools_read.catalog()
    assert [t.name for t in cat] == ["web_search", "read_widget", "recall", "about_self", "find_tool"]
    assert all(t.effect_class is EffectClass.READ for t in cat)
    assert {t.name for t in cat if t.core} == {"web_search", "find_tool"}
    assert tools_read.derive("messaging.send_new", True) is EffectClass.LEAVES      # a declared leaving type
    assert tools_read.derive("", False) is EffectClass.WRITE                        # declares more than reading


def test_the_search_door_gets_the_proposal_and_no_judge():
    seen = {}

    def find(q, **kw):
        seen.update(q=q, **kw)
        r = SearchResult(query=q, route="inline_fact", answer="w1")
        r.sources = [Source(name="p1", url="https://a.example/1")]
        return r

    got = _call(tools_read.ReadTools(find=find), "web_search", {"query": "w0"})
    assert seen["judge"] is None and seen["proposal"] == "web_search" and seen["q"] == "w0"
    assert got.status == "ok" and got.data["answer"] == "w1"
    assert [e.source for e in got.evidence] == ["https://a.example/1"]
    assert all(e.value is None for e in got.evidence)                       # unstructured: it binds no claim


def test_recall_leaves_no_reinforcement(monkeypatch):
    from memory import api as memory
    seen = {}

    def query(q, **kw):
        seen.update(kw)
        return {"memories": [{"id": 7, "text": "w2"}]}

    monkeypatch.setattr(memory, "query", query)
    got = _call(tools_read.ReadTools(), "recall", {"query": "w0"})
    assert seen.get("reinforce_used") is False and got.data["memories"] == [{"id": 7, "text": "w2"}]


def test_a_door_that_fails_is_a_result_and_an_unknown_name_is_rejected():
    def find(q, **kw):
        raise RuntimeError("w3")
    got = _call(tools_read.ReadTools(find=find), "web_search", {"query": "w0"})
    assert got.status == "failed" and "w3" in got.data["error"]
    assert _call(tools_read.ReadTools(), "send_message", {}).status == "rejected"


def test_through_the_manager_a_write_is_refused_by_the_gateway(store):
    from conversation.ports import Done as D, ToolCall
    from tests.conversation.unit.convkit import Harness
    from conversation.testing.scripted_model import reply
    h = Harness(store, grace=False)
    h.conv.tools = tools_read.ReadTools(find=lambda q, **kw: SearchResult(query=q))
    h.conv.gw.specs = lambda: {t.name: t for t in tools_read.catalog()}
    h.model.default = lambda ids: [ToolCall("c", "send_message", {"to": "w4"}), D()] \
        if len(h.model.calls) == 1 else [reply("w5"), D()]
    h.typed("w0", 100)
    h.at(1000).pump()
    refused = [p for k, lab, p in h.tel.events if k == "conv_effect" and lab == "refused"]
    assert refused and refused[0]["reason"] == "unknown_tool"


class _Relayed:
    async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role):
        metrics.update(model="m_standin", provider="p2", relayed_from="m_main", relayed_to="m_standin")
        on_tool_call("reply", {"text": "w6"})
        if False:
            yield ""


def test_which_provider_answered_reaches_the_runs_model_done(store):
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=False)
    h.conv.model = FastModel(_Relayed(), spec="s")
    h.typed("w0", 100)
    h.at(1000).pump()
    done = [p for k, lab, p in h.tel.events if k == "conv_run" and lab == "model_done"]
    assert done and done[0]["usage"]["relayed_from"] == "m_main" and done[0]["usage"]["provider"] == "p2"
    assert {"model", "provider", "relayed_from", "relayed_to"} <= set(DONE_KEYS)

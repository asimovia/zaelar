"""A peer's turn on a cluster is composed by the connector itself, and enters the manager as an event (node 13.139,
E7d-3, R-2).

The system is the language pack's own data with the agent's name and his language, and reads nothing of his memory;
the model is called once, with no act at all unless the cluster's permission grants errands — then only the declared
`start_task`, and its call starts an errand with the permission's bounded context, never his trust; the reply is made
sayable before the bridge gets it. With the conversation manager on, the turn enters it as an EVENT and its work runs
there, its reply coming back to the bridge; off, it runs where it was asked.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.meshkore import compose


def test_the_system_is_language_data_and_reads_nothing_of_his(monkeypatch):
    from i18n import langs
    from nucleo.self import snapshot
    monkeypatch.setattr(snapshot, "name", lambda: "W_Zed")
    monkeypatch.setattr(langs, "words", lambda key, *a, **k: "I am {name}; asides in {op_lang}"
                        if key == "meshkore.cluster_system" else "")
    monkeypatch.setattr("memory.api.state", lambda *a, **k: (_ for _ in ()).throw(AssertionError("his memory read")))
    assert compose.system().startswith("I am W_Zed; asides in ")


def test_only_a_granted_errand_is_offered_and_it_starts_with_the_bounded_context(monkeypatch):
    from nucleo.acts import errand
    assert compose.tools(set()) == [] and compose.tools({"web_search"}) == []
    offered = compose.tools({"escalate_to_slowbrain"})
    assert [t["function"]["name"] for t in offered] == ["start_task"]
    assert list(offered[0]["function"]["parameters"]["properties"]) == ["request"]
    born = []
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: born.append((req, context)) or 1)
    compose._on_tool_call({"src": "cluster", "trusted": False})("start_task", {"request": "w_build it"})
    compose._on_tool_call({"src": "cluster"})("send_message", {"request": "w_other", "to": "w_x"})
    assert born == [("w_build it", {"src": "cluster", "trusted": False})]


def test_the_reply_is_sayable_and_one_call_is_made(monkeypatch):
    from nucleo.llm import fast_client, provider_chain
    calls = []

    class _Client:
        async def complete(self, messages, **kw):
            calls.append((messages, kw.get("tools")))
            return "w_hi. w_hi. w_there"
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    monkeypatch.setattr(provider_chain, "pick", lambda *a, **k: {"name": "w_tier"})
    monkeypatch.setattr(provider_chain, "spec_for", lambda tier: None)
    monkeypatch.setattr(compose, "system", lambda: "w_system")
    assert asyncio.run(compose.respond("w_peer says")) == "w_hi. w_there"
    assert len(calls) == 1 and calls[0][0][1]["content"] == "w_peer says" and calls[0][1] is None


def test_with_the_manager_on_the_turn_enters_as_an_event_and_its_reply_comes_back(monkeypatch):
    from nucleo.conversation_host import entry, events_in
    got = []

    async def respond(text, **kw):
        return f"w_reply to {text}"
    monkeypatch.setattr(compose, "respond", respond)
    monkeypatch.setattr(events_in, "_on", lambda: False)
    assert asyncio.run(compose.turn("w_a")) == "w_reply to w_a"            # off: here
    monkeypatch.setattr(events_in, "_on", lambda: True)
    monkeypatch.setattr("nucleo.conversation_host.boot.account", lambda: "acct-w")

    def hand(fn):
        class _Conv:
            def give(self, env):
                got.append(env)
                asyncio.get_running_loop().create_task(events_in.HostEvents().run("acct-w", env))
        loop = asyncio.get_running_loop()
        loop.call_soon(fn, _Conv())
    monkeypatch.setattr(entry, "_hand", hand)
    assert asyncio.run(compose.turn("w_b")) == "w_reply to w_b"
    assert got[0].body.origin == compose.ORIGIN and got[0].body.route == {"as": events_in.WORK}
    long = "w_c " * 3000
    assert asyncio.run(compose.turn(long)) == f"w_reply to {long}"
    assert got[1].body.text == long, "the peer's turn enters the conversation whole"


def test_a_huge_peer_turn_the_providers_refuse_fails_out_loud(monkeypatch):
    """A peer's turn of 100 000 characters enters whole (no cut), and when the provider refuses it for its size and so
    does the relay, the turn FAILS — the bridge says it on the cluster's wall (`error`), never a silent empty reply."""
    from connectors.meshkore.bridge import turn as bridge_turn
    from nucleo.conversation_host import events_in
    from nucleo.llm import fast_client, provider_chain
    calls = []

    class _Client:
        async def complete(self, messages, **kw):
            calls.append(len(messages[1]["content"]))
            raise RuntimeError("400 context_length_exceeded: the prompt is too long")
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    tiers = iter([{"name": "w_titular"}, {"name": "w_relay"}])
    monkeypatch.setattr(provider_chain, "pick", lambda *a, **k: next(tiers))
    monkeypatch.setattr(provider_chain, "note_failure", lambda err, tier=None: {"name": "w_relay"}
                        if tier and tier["name"] == "w_titular" else None)
    monkeypatch.setattr(provider_chain, "spec_for", lambda tier: None)
    monkeypatch.setattr(compose, "system", lambda: "w_system")
    monkeypatch.setattr(events_in, "_on", lambda: False)
    huge = "w " * 50_000
    with pytest.raises(RuntimeError, match="context_length_exceeded"):
        asyncio.run(compose.turn(huge))
    assert calls == [len(huge), len(huge)], "whole, to the titular and once to the relay"
    src = __import__("inspect").getsource(bridge_turn)
    assert '_b._emit("error", f"cluster brain turn failed: {e}")' in src, "the failure is said on the cluster's wall"

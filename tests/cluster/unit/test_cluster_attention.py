"""A cluster wakes the brain only for what its subscription attends to.

Measured on a live engine: every ~100 s the heartbeat ran a full brain turn «[cluster:commons · heartbeat] no reply
for a while and peers are online…» on the public Commons, plus «you just connected; agents online you've never talked
to…» intros — model work nobody asked for. Every subscription now carries attention flags (`addressed_to_me`,
`general_messages`, `generated_content`), defaults by kind (public → only addressed; private → everything), and
`_brain_turn(kind=…)` asks `attention.wakes` before opening anything.

Disarm: make `attention.wakes` return True, or drop the gate at the top of `_brain_turn`, or the `_attends` in
`note_objective` → red.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from connectors.meshkore import attention, store


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CONFIG_FILE", Path(tmp_path) / "meshkore.json")
    store.save_cluster("commons", "c_pub", "", "zaelar", vis="public")
    store.save_cluster("friends", "c_priv", "tok-private-123", "zaelar")


@pytest.fixture
def br(cfg, monkeypatch):
    from connectors.meshkore import bridge
    monkeypatch.setattr(bridge, "_emit", lambda *a, **k: None)

    class _Client:
        def __init__(self, public):
            self.public, self.online, self.handle = public, {"wanderer"}, "zaelar"

    clients = {"commons": _Client(True), "friends": _Client(False)}

    class _Mgr:
        def get(self, name): return clients.get(name)
        def has(self, name): return name in clients

    calls = []

    async def _brain(text, **_k):
        calls.append(text)
        return ""

    b = bridge.ClusterBridge(_Mgr(), brain=_brain)
    b._now = lambda: 1000.0
    b._notify_registry = lambda: None
    b.calls = calls
    return b


def _msg(cluster, to=None, text="anyone around?"):
    return {"kind": "message", "cluster": cluster, "from": "wanderer", "to": to, "payload": {"text": text}}


def _run(b, ev):
    async def _go():
        await b.on_event(ev)
        while b._turns:
            await asyncio.gather(*list(b._turns), return_exceptions=True)
    asyncio.run(_go())


# ── defaults written with every subscription ───────────────────────────────────────────────────────────────────
def test_a_new_subscription_gets_the_defaults_of_its_kind(cfg):
    raw = store.load_clusters()
    assert raw["commons"]["attention"] == {"addressed_to_me": True, "general_messages": False, "generated_content": False}
    assert raw["friends"]["attention"] == {"addressed_to_me": True, "general_messages": True, "generated_content": True}


def test_a_resave_keeps_his_flags(cfg):
    store.set_attention("commons", {"general_messages": True, "bogus": True})
    store.save_cluster("commons", "c_pub", "", "zaelar", vis="public")
    assert store.get_attention("commons")["general_messages"] is True
    assert "bogus" not in store.load_clusters()["commons"]["attention"]


def test_existing_subscriptions_are_migrated(cfg):
    d = store.load_clusters()
    for c in d.values():
        c.pop("attention")
    store._write(d)
    assert sorted(store.migrate_attention()) == ["commons", "friends"]
    assert store.load_clusters()["commons"]["attention"]["general_messages"] is False
    assert store.load_clusters()["friends"]["attention"]["general_messages"] is True
    assert store.migrate_attention() == []


# ── the door ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_broadcast_arrives_with_to_null_and_is_general():
    assert attention.classify({"to": None}) == "general"
    assert attention.classify({}) == "general"
    assert attention.classify({"to": "*"}) == "general"
    assert attention.classify({"to": "zaelar"}) == "addressed"


def test_commons_general_message_does_not_wake(br):
    _run(br, _msg("commons"))
    assert br.calls == []
    assert "commons" not in br._last_peer_msg, "an unattended message must not feed the heartbeat's context"


def test_commons_message_addressed_to_us_wakes(br):
    _run(br, _msg("commons", to="zaelar"))
    assert len(br.calls) == 1


def test_commons_connect_intro_does_not_wake(br, monkeypatch):
    from connectors.meshkore import mem_ingest
    monkeypatch.setattr(mem_ingest, "known_peer", lambda c, p: False)
    _run(br, {"kind": "ready", "cluster": "commons", "online": ["wanderer"]})
    _run(br, {"kind": "presence", "cluster": "commons", "agent": "stranger", "status": "online"})
    assert br.calls == []


def test_commons_is_not_engaged_by_being_subscribed_so_the_heartbeat_never_nudges(br):
    br.note_objective("commons")
    br.note_objective("friends")
    assert br._engaged["commons"] is False
    assert br._engaged["friends"] is True


def test_a_turn_on_commons_cannot_open_as_general_traffic(br):
    asyncio.run(br._brain_turn("commons", "[cluster:commons · event] you just connected"))
    assert br.calls == []


def test_private_cluster_defaults_wake_on_general_and_content(br):
    _run(br, _msg("friends"))
    assert len(br.calls) == 1
    assert attention.wakes("friends", "content") is True
    assert attention.wakes("commons", "content") is False

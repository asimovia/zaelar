"""Failover and back, a reconnect, a lost voice and an empty answer (node 13.100, V2-941, v3.1 B8g — the audit of
B8c–B8e + B7i, TI-3 and TI-4; TI-1 and TI-2 are in 13.92).

  · a voice of his that lasted and was cut by a stall or a hole in the line with no word heard is not «nothing»: it
    is an entry with no words, which runs no model and owes him «I lost that»; a short wordless one is still a
    discard;
  · a `reply` with no text is never published as an answer: one repair round, then the language's failure line;
  · an answer cut by its token ceiling is a failure, never half an order carried out, and the ceiling of a call is
    never below what an order needs.
"""
from __future__ import annotations

import asyncio

from conversation.ear import signals as S
from conversation.ports import Done, PromptParts
from conversation.testing.scripted_model import reply
from nucleo.conversation_host import model
from tests.conversation.unit.convkit import Harness


class _Words:
    def line(self, key, near=""):
        return "w_lost" if key == "mute_lines" else ""


def test_a_voice_that_lasted_and_was_cut_by_a_hole_is_owed_the_line(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    h.model.default = lambda ids: [reply("w9"), Done()]
    h.hear(S.VadEdge("d1", "rise", 10))
    h.hear(S.LinkGap("d1", 4000))                                             # 4 s of his voice, no word heard
    h.settle(10_000)
    assert h.model.calls == [] and "conv:failed:r_iv_000001" in h.owed.rows
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "no_words")]


def test_a_short_wordless_voice_cut_by_a_hole_is_still_a_discard(store):
    h = Harness(store, grace=False)
    h.hear(S.VadEdge("d1", "rise", 10))
    h.hear(S.LinkGap("d1", 400))
    h.settle(10_000)
    assert h.closes() == [] and h.owed.rows == {}


def test_a_hole_with_nothing_open_is_said_once_as_a_gap_never_as_an_ending(store):
    h = Harness(store, grace=False)
    h.hear(S.LinkGap("d1", 400))                                              # no voice open: nothing to end
    ear = [(lab, p.get("reason")) for k, lab, p in h.tel.events if k == "conv_ear"]
    assert ear == [("gap", "link_gap")] and h.closes() == [] and h.owed.rows == {}


def test_an_empty_reply_is_never_published(store):
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    rounds = [[reply(""), Done()], [reply("w8"), Done()]]
    h.model.default = lambda ids: rounds[min(len(h.model.calls) - 1, len(rounds) - 1)]
    h.typed("w1", 10)
    h.settle(2000)
    assert [o.text for o in h.mouth.orders] == ["w8"]                          # repaired
    from conversation.store.memory import MemoryStore
    h2 = Harness(MemoryStore(), grace=False)                                   # a conversation of its own
    h2.conv.words = _Words()
    h2.model.default = lambda ids: [reply("  "), Done()]
    h2.typed("w1", 10)
    h2.settle(2000)
    assert [o.text for o in h2.mouth.orders] == ["w_lost"]                     # twice empty: the failure line


class _Client:
    def __init__(self, finish):
        self.finish = finish

    async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role, **kw):
        metrics.update(finish_reason=self.finish)
        on_tool_call("reply", {"text": "w1 w2", "claims": []})
        if False:
            yield ""


def _events(finish):
    async def go():
        return [ev async for ev in model.FastModel(_Client(finish), spec="s").stream(
            PromptParts("w0", "", (), "w1", (), "voice"), [], run_id="r", model_id="")]
    return [type(e).__name__ for e in asyncio.run(go())]


def test_an_answer_cut_by_its_ceiling_is_a_failure_never_half_an_order():
    assert _events("length") == ["Done", "Failed"]
    assert _events("tool_calls") == ["Done", "Command"]


def test_a_calls_ceiling_leaves_room_for_the_order(monkeypatch):
    import genome
    g = genome.genesis()
    monkeypatch.setattr(genome, "genesis", lambda: {**g, "conversation": {**g["conversation"],
                                                                         "max_tokens": {"voice": 50}}})
    assert model.max_tokens("voice") == model.ORDER_ROOM


def test_a_provider_gone_quiet_while_his_voice_is_up_is_a_gap_once():
    """The voice process knows the audio flows: his voice up and no message of the provider for a while is a gap (what
    the ear was hearing is being lost) — once, until the provider speaks again."""
    from voice.engine.pipeline import ear_tap
    facts = []
    tap = ear_tap.Tap("holder", facts.append)
    tap.new_stream()
    tap.on_message({"type": "TurnInfo", "event": "Update", "turn_index": 0, "audio_window_end": 0.5, "words": []})
    tap.last_msg_ms = 1000
    for t in range(1000, 1000 + ear_tap.PROVIDER_STALL_MS + 900, 30):
        tap.edges.frame(True, t)
    assert [f["t"] for f in facts].count("gap") == 1


def test_his_voice_lost_ends_the_manual_session_and_new_ones_take_the_old_path(monkeypatch):
    import importlib
    from types import SimpleNamespace
    entry = importlib.import_module("nucleo.conversation_host.entry")
    switch = importlib.import_module("nucleo.conversation_host.switch")
    rs = importlib.import_module("voice.remote_session")
    words = importlib.import_module("nucleo.conversation_host.words")
    notices = importlib.import_module("nucleo.pulse.notices")
    posts = []

    async def notify(*a, **k):
        return None
    monkeypatch.setattr(notices, "notify", notify)
    monkeypatch.setattr(words.PackWords, "line", lambda self, key, near="": "w_lost")
    monkeypatch.setattr(importlib.import_module("voice.observer"), "emit", lambda *a, **k: None)
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(True, "voice")))
    monkeypatch.setitem(rs._M, "client", SimpleNamespace(post_soon=lambda path, body: posts.append(path)))
    entry.reset()
    try:
        entry.voice_lost()
        assert posts == ["/voice/close"] and entry.broken()
        assert "could not open" in switch.refused()                           # the session that reconnects: old path
    finally:
        entry._opener["broken_until"] = 0
        entry.reset()

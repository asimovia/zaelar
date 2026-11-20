"""A voice that was lost is told with the text that follows, and every answer reaches the record (node 13.43, v3.1
B4: U44 and the `conv` pair).

U44: his voice reached nothing whole — rose and fell with no word, was thrown out by a guard, or ended incomplete —
and within the window he types: that text's prompt carries the fact, how long ago and why. The tail of the voice
that just closed and our own voice heard back are no lost voice; outside the window, or with no text in the batch,
nothing is added.

The record: each answered batch owes one pair (what he said, what we answered) to the host's `Record` port, at least
once — a port that fails keeps it owed, the sweep hands it over, a new process hands over what the dead one owed. A
silent close records nothing. The host's adapter writes the engine's `kind='conv'` row, so «what did I tell you»
finds a switched session's conversation. The state comes from the engine's own readers — STATE, the widgets, the
tasks — each bounded within the run's budget; a reader that fails leaves its block out; the notices owed are not
among them (the manager says those lines itself: in the state too, one would be told twice).
"""
from __future__ import annotations

from conversation.config import Config

import asyncio

import pytest

from conversation.ear import signals as S
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from nucleo.conversation_host.record import MemoryRecord
from tests.conversation.unit.convkit import Harness


def _rise_and_fall(h: Harness, t: int, ep: str = "d1") -> None:
    h.hear(S.VadEdge(ep, "rise", t), *h.beats(t, t + 600), S.VadEdge(ep, "fall", t + 600),
           *h.beats(t + 600, t + 4000))


def _state(h: Harness) -> str:
    return h.model.calls[-1].prompt.state


def test_a_voice_with_no_word_then_a_text_tells_it(store):
    h = Harness(store, grace=False)
    _rise_and_fall(h, 1000)
    h.typed("w1", 20_000)
    h.at(21_000).pump()
    state = _state(h)
    assert "VOICE LOST" in state and "no_words" in state


def test_past_the_window_or_with_no_text_nothing_is_added(store):
    h = Harness(store, grace=False)
    _rise_and_fall(h, 1000)
    h.typed("w1", 1000 + h.conv.cfg.voice_lost_window_ms + 5000)
    h.at(h.clock.mono + 1000).pump()
    assert "VOICE LOST" not in _state(h)
    h.utter([(["w2"], 0)], at=h.clock.mono + 2000)
    assert "VOICE LOST" not in _state(h)


def test_an_incomplete_voice_then_a_text_tells_it_with_its_reason(store):
    h = Harness(store, grace=False)
    t = 1000
    ws = h.words(["w3"], t)
    h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 7, 1, False, ws, (t, ws[-1][2])))
    h.at(t + 30_000).pump()                                      # it stalled: delivered incomplete
    h.typed("w4", t + 31_000)
    h.at(t + 32_000).pump()
    state = _state(h)
    assert "VOICE LOST" in state and "s ago" in state


def test_the_tail_of_a_closed_voice_is_no_lost_voice(store):
    from conversation.composer.compose import NOT_LOST
    assert "no_voice" in NOT_LOST and "echo" in NOT_LOST


class _Record:
    def __init__(self, fail: int = 0) -> None:
        self.pairs, self.fail = [], fail

    def pair(self, account, said, answered, *, ref, channel="voice"):
        if self.fail:
            self.fail -= 1
            raise OSError("w0")
        self.pairs.append((said, answered, ref))


def test_an_answered_batch_owes_one_pair_and_a_silent_one_none(store):
    rec = _Record()
    h = Harness(store, grace=False)
    h.conv.record = rec
    h.typed("w5", 100)
    h.at(1000).pump()
    assert len(rec.pairs) == 1 and rec.pairs[0][0] == "w5" and rec.pairs[0][1] == h.mouth.orders[0].text
    from conversation.ports import Command, Done
    h.model.default = lambda ids: [Command("no_reply", {"reason": "w0"}), Done()]
    h.typed("w6", 2000)
    h.at(3000).pump()
    assert len(rec.pairs) == 1


def test_a_port_that_fails_keeps_the_pair_owed_and_the_sweep_hands_it_over(store):
    rec = _Record(fail=1)
    h = Harness(store, config=Config(collect_ms=350), grace=False)           # the run at 1000, before any sweep
    h.conv.record = rec
    h.typed("w5", 100)
    h.at(1000).pump()
    assert not rec.pairs and "conv_close/record_failed" in h.tel.labels()
    h.conv.sweep(2000)
    assert len(rec.pairs) == 1
    h.conv.sweep(3000)
    assert len(rec.pairs) == 1                                         # handed over once, then done


def test_a_new_process_hands_over_what_the_dead_one_owed(store):
    h = Harness(store, grace=False)
    h.conv.record = _Record(fail=99)
    h.typed("w5", 100)
    h.at(1000).pump()
    rec = _Record()
    h2 = Harness(store, grace=False)
    h2.conv.record = rec
    h2.conv.recover()
    assert [p[0] for p in rec.pairs] == ["w5"]


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    monkeypatch.setattr(memapi, "write", lambda text, **kw: memwriter.insert_memory(text, **kw))
    yield
    memdb.reset_db()
    mememb.reset()


def test_what_did_i_tell_you_finds_a_switched_sessions_pair(fresh_db):
    MemoryRecord().pair("a", "the train to Lyon leaves at nine", "Noted, the Lyon train at nine", ref="run_1")
    lines = memapi.conversation(hours=1, query="train Lyon")
    assert any("Lyon" in ln["text"] for ln in lines if ln["who"] == "operator")
    assert any("Lyon" in ln["text"] for ln in lines if ln["who"] == "assistant")


def test_the_state_comes_from_the_engines_readers_bounded_and_a_failing_one_left_out(monkeypatch):
    from nucleo.conversation_host import memory_read

    def broken():
        raise OSError("w0")

    monkeypatch.setattr(memory_read, "READERS", (("STATE", lambda: "w" * 10_000), ("TASKS", broken),
                                                 ("NOTICES", lambda: "w7")))
    blocks = asyncio.run(memory_read.MemoryRead().state_blocks("a", budget_tokens=300))
    assert [b.title for b in blocks] == ["STATE", "NOTICES"]
    assert len(blocks[0].text) == 300 * memory_read.CHARS_PER_TOKEN // memory_read.BLOCK_SHARE   # never the whole budget
    assert sum(len(b.text) for b in blocks) <= 300 * memory_read.CHARS_PER_TOKEN


def test_the_notices_owed_are_not_in_the_state():
    from nucleo.conversation_host import memory_read
    assert "NOTICES" not in [t for t, _r in memory_read.READERS]


def test_his_words_of_an_answered_batch_are_filed_with_their_channel(monkeypatch):
    """What he tells the agent is remembered (C14b): the pair of an answered batch hands his words to the memory's one
    writer, typed or voice as they came — a silent batch has no pair, so nothing of another voice is ever filed."""
    import asyncio

    from nucleo import memory_agent
    from nucleo.conversation_host import record
    seen = []

    async def ingest(text, *, role="operator", channel="voice"):
        seen.append((text, role, channel))
    monkeypatch.setattr(memory_agent, "ingest_utterance", ingest)
    monkeypatch.setattr(memapi, "write", lambda *a, **k: None)

    async def go():
        record.MemoryRecord().pair("a", "w_my_daughter_is_w_lia", "w_noted", ref="run_9", channel="typed")
        record.MemoryRecord().pair("a", "", "w_noted", ref="run_10")
        await asyncio.sleep(0)
    asyncio.run(go())
    assert seen == [("w_my_daughter_is_w_lia", "operator", "typed")]

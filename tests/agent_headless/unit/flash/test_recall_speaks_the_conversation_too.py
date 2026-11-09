"""A recall speaks the conversation too: its block carries the matching turns from outside the live window (V2-865).

The failure: the model's `recall` read only the durable pills (`mid`/`long`); the pill kept of the episode
described the artist he had asked for without the name, which was in zaelar's own reply three hours back in the
`conv` buffer. Three recalls, three «nothing names that artist».

Pinned here:
  · `compose_recall(query)` returns the «Lo hablado antes» lines even when no durable pill
    matched, each with its time, his words and the reply;
  · never a line from the newest `LIVE_WINDOW_TURNS` turns — they are already in front of the model;
  · `timings["recall_conv_turns"]` counts the lines it carried;
  · `LIVE_WINDOW_TURNS` is half the dialog window (`_WINDOW_MAX` messages = turns × 2), in both places it is read.
"""
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_MEM_OBSERVABILITY", "0")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _turn(u: str, a: str, ago_s: int) -> int:
    mid = memwriter.insert_memory(f"Operador: {u} · zaelar: {a}", kind="conv", level="short", importance=0.2,
                                  ttl_days=2.0, meta={"source": "conv", "u": u, "a": a})
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (int(time.time()) - ago_s, mid))
    return mid


QUERY = "the artist from the television series whose song he asked to play"


def test_the_recall_block_carries_the_old_turn_when_no_pill_matched(fresh_db):
    from nucleo.turn.prompt import recall
    _turn("play me a song by the actress who sings in that television series",
          "That is the lead artist of the series; playing her song now", 3 * 3600)
    for i in range(5):                                       # the live window: it repeats the words too
        _turn(f"the artist from the television series, I told you {i}", f"no artist on record {i}", (5 - i) * 60)
    timings: dict = {}
    block, _used = recall.compose_recall(QUERY, timings, lexical_only=True)
    assert "Lo hablado antes, literal y con hora:" in block
    assert "Puede que venga a cuento" not in block, "no durable pill matched: the conversation lane stands alone"
    assert "él: «play me a song by the actress" in block and "playing her song now" in block
    for i in range(5):
        assert f"I told you {i}" not in block and f"no artist on record {i}" not in block, "the live window is out"
    assert timings["recall_conv_turns"] == 1


def test_nothing_matched_anywhere_is_an_empty_block(fresh_db):
    from nucleo.turn.prompt import recall
    _turn("what time is it", "Ten past nine", 3 * 3600)
    timings: dict = {}
    block, _used = recall.compose_recall("zzqx nonexistent", timings, lexical_only=True)
    assert block == "" and timings["recall_conv_turns"] == 0


def test_the_live_window_is_half_the_dialog_window():
    from memory import _prompt as memprompt
    from nucleo.turn import pipeline_failure
    from nucleo.turn.prompt import recall
    assert recall.LIVE_WINDOW_TURNS == pipeline_failure._WINDOW_MAX // 2
    assert memprompt.reads.LIVE_WINDOW_TURNS == pipeline_failure._WINDOW_MAX // 2

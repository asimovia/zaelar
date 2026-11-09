"""Recall's conversation reader picks the turn that ANSWERED, not the echoes of the request (V2-865, second cut).

Measured 2026-11-09 on build 118, replaying «I did ask you some time ago to put some music here… get the same
name of the artist and play it»: the relevance pick was crowned by turns ABOUT the earlier request — his own
earlier attempt at the same sentence (whose reply named the wrong artist), five turns of one complaint episode
that shared its words, and turns carrying «asked», «earlier», «today» — while the one turn, hours older, that
named the artist waited below the limit.

Pinned here:
  · a row whose operator words are mostly the query's own (`REPEAT_OVERLAP`) is his earlier attempt, not the
    referent, and is dropped;
  · a relevance pick takes at most `EPISODE_ROWS` turns of one episode, so an older episode gets in;
  · the words of a REFERENCE to the conversation («asked», «earlier», «today», «pedí», «antes», «hoy»…) are
    not search terms.
"""
import time

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import history as memhistory
from memory import writer as memwriter
from memory.retriever import _fts_query

H = 3600


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
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


def _ids(lines: list[dict]) -> set[int]:
    return {ln["id"] for ln in lines}


QUERY = "put some music here by the singer from the series and play her song"


def test_his_earlier_attempt_at_the_same_request_is_not_the_referent(fresh_db):
    answer = _turn("play something by the lead of that series", "That is the lead singer, playing her now", 5 * H)
    attempt = _turn("put some music here by the singer from the series and play her song please",
                    "Playing a song by the wrong singer", 2 * H)
    lines = memapi.conversation(hours=48, query=QUERY, limit=4, by="relevance")
    assert attempt not in _ids(lines), "his own earlier attempt carries the answer that did not satisfy him"
    assert answer in _ids(lines)


def test_a_short_query_never_counts_as_a_repeat():
    words = memhistory._words("play her song")
    assert not memhistory._is_repeat(words, words), "under four words a query is too thin to call a repeat"


def test_one_episode_cannot_fill_the_pick(fresh_db):
    answer = _turn("a song by the singer of the series", "Here is the lead singer of the series", 5 * H)
    complaint = [_turn(f"no, the singer of the series, her song number {i}", f"which singer of the series {i}?",
                       H + (6 - i) * 60) for i in range(6)]
    lines = memapi.conversation(hours=48, query=QUERY, limit=4, by="relevance")
    got = _ids(lines)
    assert len(got & set(complaint)) <= memhistory.EPISODE_ROWS, "one episode said five ways is still one episode"
    assert answer in got, "the turn that answered, hours older, gets the room the episode cap leaves"


@pytest.mark.parametrize("sentence", [
    "I asked you earlier today about it",
    "the request from some messages ago",
    "you mentioned it some minutes ago in this conversation",
    "te lo pedí antes, hoy, hace un rato",
    "lo hablamos ayer, hace horas",
])
def test_the_words_of_a_reference_are_not_search_terms(sentence):
    assert _fts_query(sentence) == "", f"{sentence!r} carries only the words of a reference: {_fts_query(sentence)!r}"


def test_a_reference_beside_the_subject_searches_the_subject(fresh_db):
    answer = _turn("the singer of the series", "That is the lead of the series", 4 * H)
    for i in range(6):
        _turn(f"I asked you earlier today, you told me before {i}", f"you asked me earlier today {i}",
              2 * H + (6 - i) * 60)
    lines = memapi.conversation(hours=48, query="the singer I asked you about earlier today", limit=2,
                                by="relevance")
    assert answer in _ids(lines), "«asked», «earlier», «today» crowned the complaint over the answer"

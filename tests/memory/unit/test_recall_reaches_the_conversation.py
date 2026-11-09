"""Recall reaches the conversation: the turn that ANSWERS outranks the live complaint that repeats the words (V2-865).

The failure: the model's own recall query was answered by the conversation reader with the newest matching turns —
twelve turns of the live complaint («the artist… you told me earlier…») — and the one turn, three hours old,
whose reply held the name was trimmed by recency.

Pinned here:
  · `conversation(query, by="relevance")` picks the turns carrying the most DISTINCT query terms first, and with
    the live window left out (`skip_newest`) the old answer is in; `by="recency"` with the same bounds is not —
    that is why relevance exists;
  · `skip_newest` leaves out exactly the newest N turns;
  · the output stays chronological whatever the pick;
  · `is_kickoff` recognises the first-turn kickoff of every supported language and nothing else.
"""
import time

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import history as memhistory
from memory import writer as memwriter


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


QUERY = "the artist from the television series whose song he asked to play"


def _the_day() -> int:
    """One old turn that answers, then twelve recent turns of the complaint that repeat ONE word of the query."""
    old = _turn("play me a song by the actress who sings in that television series",
                "That is the lead artist of the series; playing her song now", 3 * 3600)
    for i in range(12):
        _turn(f"I already told you about the artist {i}", f"I do not have that artist {i}", (12 - i) * 60)
    return old


def _ids(lines: list[dict]) -> set[int]:
    return {ln["id"] for ln in lines}


def test_relevance_reaches_the_old_turn_that_answers(fresh_db):
    old = _the_day()
    lines = memapi.conversation(hours=48, query=QUERY, limit=4, by="relevance", skip_newest=5)
    assert old in _ids(lines), [ln["text"] for ln in lines]
    assert any("playing her song now" in ln["text"] for ln in lines if ln["who"] == "assistant")


def test_recency_with_the_same_bounds_buries_it(fresh_db):
    old = _the_day()
    lines = memapi.conversation(hours=48, query=QUERY, limit=4, by="recency", skip_newest=5)
    assert lines, "the complaint matches the query too"
    assert old not in _ids(lines), "recency keeps the live complaint — the reason `by=relevance` exists"


def test_skip_newest_leaves_out_exactly_the_newest_turns(fresh_db):
    ids = [_turn(f"turn {i}", f"reply {i}", (20 - i) * 60) for i in range(20)]
    kept = _ids(memapi.conversation(hours=24, limit=40, skip_newest=5))
    assert kept == set(ids[:-5])
    assert _ids(memapi.conversation(hours=24, limit=40, skip_newest=0)) == set(ids)


def test_the_output_stays_chronological_whatever_the_pick(fresh_db):
    _the_day()
    lines = memapi.conversation(hours=48, query=QUERY, limit=4, by="relevance", skip_newest=5)
    ts = [float(ln["ts"]) for ln in lines]
    assert len({ln["id"] for ln in lines}) >= 2 and ts == sorted(ts)


def test_is_kickoff_knows_every_languages_kickoff_and_nothing_else():
    from i18n import langs
    prompts = [sp.kickoff_prompt for sp in langs.supported() if sp.kickoff_prompt]
    assert len(prompts) >= 2
    for p in prompts:
        assert memhistory.is_kickoff(p), p
        assert memhistory.is_kickoff("  " + p.replace(" ", "\n ", 1) + " "), "whitespace is not a difference"
    for other in ("", "hola", "put some music here", prompts[0][:40], prompts[0] + " Also open my agenda."):
        assert not memhistory.is_kickoff(other), other

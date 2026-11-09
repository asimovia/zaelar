"""The live window is the LIVE CHAIN, not «the newest five» (V2-865, second cut).

Measured 2026-11-09 on build 118: a request made at midnight was among the newest five `conv` rows the next
morning, so the day's schema skipped it as «already in the window» — and the window, seeded at the session's
start, held the tail of that old session, including the model's own «I don't have what we said earlier today».
The request was in neither place the model reads.

Pinned here:
  · `history.live_conv_ids(n, gap_min)` takes the newest `n` rows only while they chain to now with gaps under
    `gap_min` minutes; after a night's silence it is EMPTY; `gap_min=None` is the plain «newest n»;
  · `recent_window(gap_min=…)` returns only the live episode, and the window seed of a turn passes that gap;
  · `day_ledger` skips the live chain only, so the midnight request is in the morning's schema;
  · the day's episodes and the live window are cut by ONE silence (`EPISODE_GAP_MIN is LIVE_GAP_MIN`).
"""
import ast
import time
from pathlib import Path

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import history as memhistory
from memory import writer as memwriter
from memory._prompt import reads as memreads

ENGINE = Path(__file__).resolve().parents[3]
H = 3600


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("ZAELAR_DAY_HOURS", raising=False)
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


def _last_night() -> list[int]:
    """A session that ended nine hours ago: the request, the answer, then the model's own refusal."""
    return [_turn("put on a song by the singer from that series", "Here is the lead singer's song", 9 * H + 240),
            _turn("louder please", "Done", 9 * H + 120),
            _turn("the same one again", "I don't have what we said earlier today", 9 * H)]


def test_after_a_nights_silence_the_live_chain_is_empty(fresh_db):
    old = _last_night()
    assert memhistory.live_conv_ids(5) == set(), "nothing chains to now: the window holds none of last night"
    assert memhistory.live_conv_ids(5, gap_min=None) == set(old), "the plain reading is still «the newest n»"


def test_the_live_chain_stops_at_the_first_silence(fresh_db):
    _last_night()
    live = [_turn("good morning, open my agenda", "It is open", 300), _turn("and the weather?", "Sunny", 60)]
    assert memhistory.live_conv_ids(5) == set(live)
    assert memhistory.live_conv_ids(1) == {live[-1]}, "never more than the newest n"


def test_the_seed_reads_only_the_live_episode(fresh_db):
    _last_night()
    assert len(memapi.recent_window(limit=6)) == 6, "without a gap the window reaches back to last night"
    assert memapi.recent_window(limit=6, gap_min=memreads.EPISODE_GAP_MIN) == []
    _turn("good morning", "Good morning", 120)
    seeded = memapi.recent_window(limit=6, gap_min=memreads.EPISODE_GAP_MIN)
    assert [m["content"] for m in seeded] == ["good morning", "Good morning"], seeded
    assert not any("don't have what we said" in m["content"] for m in seeded)


def test_the_midnight_request_is_in_the_mornings_day(fresh_db):
    _last_night()
    eps = memapi.day_ledger()
    assert [e["u"] for e in eps] == ["put on a song by the singer from that series"], eps
    assert eps[0]["turns"] == 3


def test_one_silence_cuts_the_day_and_the_window():
    assert memreads.EPISODE_GAP_MIN is memhistory.LIVE_GAP_MIN


def test_the_turn_seeds_its_window_with_the_live_episode_only():
    """The seed call in the turn's admission passes the episode gap (a source guard: the call sits inside a
    coroutine that needs the whole turn to run)."""
    tree = ast.parse((ENGINE / "nucleo" / "turn" / "pipeline_admit.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "recent_window"]
    assert calls, "the window seed is gone"
    assert all(any(k.arg == "gap_min" for k in c.keywords) for c in calls), \
        "a seed without `gap_min` puts last night's tail back in front of the model as the freshest dialog"

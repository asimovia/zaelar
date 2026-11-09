"""The day is in the state: the prompt carries a SCHEMA of what was said earlier today (V2-865).

The failure: three hours after the agent itself named the artist he had asked for, a new work session asked for
«the same artist» and the model answered three times that it had no access to what was said earlier today. The
passive block «DE QUÉ ÍBAIS HABLANDO» was ≈2 turns; nothing in the prompt said the earlier episode existed.

Pinned here:
  · `day_ledger()` folds the day's `conv` buffer into EPISODES — a silence, a first-turn kickoff (flagged
    `meta.kickoff`, or the i18n `kickoff_prompt` text of any language) or `EPISODE_MAX_TURNS` opens a new one;
  · a kickoff never opens or fills an episode, and the newest `LIVE_WINDOW_TURNS` turns (the live window) are out;
  · `day_block()` renders «HOY, EN ESQUEMA» for the live tail with each episode's opener and first reply, counts it in
    its stats, keeps it under `_DAY_MAX_CHARS` by dropping the OLDEST line first, and is absent with only the
    live thread.
"""
import time

import pytest

from memory import _prompt as memprompt
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from memory._prompt import compose as memcompose


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


def _turn(u: str, a: str, ago_s: int, **meta) -> int:
    mid = memwriter.insert_memory(f"Operador: {u} · zaelar: {a}", kind="conv", level="short", importance=0.2,
                                  ttl_days=2.0, meta={"source": "conv", "u": u, "a": a, **meta})
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (int(time.time()) - ago_s, mid))
    return mid


def _kickoff_text(code: str) -> str:
    from i18n import langs
    return langs.spec(code).kickoff_prompt


def _live_thread(n: int) -> list[str]:
    said = [f"live complaint number {i}" for i in range(n)]
    for i, u in enumerate(said):
        _turn(u, f"live answer {i}", (n - i) * 60)          # the last minutes, one turn a minute
    return said


def test_the_day_is_folded_into_episodes_without_the_kickoff_or_the_live_window(fresh_db):
    h = 3600
    # Episode 1, ten hours ago, opened by a flagged kickoff row.
    _turn("Es el primer turno.", "Buenos días", 10 * h + 60, kickoff=True)
    _turn("put the weather card on screen", "There it is", 10 * h)
    _turn("and tomorrow?", "Rain tomorrow", 10 * h - 60)
    # Episode 2, six hours ago, opened by the ENGLISH kickoff text with no flag.
    _turn(_kickoff_text("en"), "Hello again", 6 * h + 60)
    _turn("find me a song by the artist from that show", "That would be the lead singer, here it is", 6 * h)
    _turn("louder", "Done", 6 * h - 60)
    # Episode 3, two minutes after episode 2 ended: only the flagged kickoff separates them.
    _turn("Es el primer turno.", "Hola", 6 * h - 180, kickoff=True)
    _turn("open my agenda", "Your agenda is open", 6 * h - 240)
    live = _live_thread(6)

    eps = memapi.day_ledger()
    openers = [e["u"] for e in eps]
    assert openers[:3] == ["put the weather card on screen", "find me a song by the artist from that show",
                           "open my agenda"], openers
    assert [e["turns"] for e in eps[:3]] == [2, 2, 1]
    assert eps[1]["a"] == "That would be the lead singer, here it is" and eps[1]["last_a"] == "Done"
    kickoffs = {"Es el primer turno.", _kickoff_text("en")}
    assert not kickoffs & set(openers), "a kickoff is the engine speaking in his voice: it never opens an episode"
    # The live window (newest 5 turns) is not in the ledger; the sixth-newest live turn is the only live trace.
    assert openers[3:] == [live[0]], openers
    assert not set(live[1:]) & set(openers)
    assert all(e["start"] <= e["end"] for e in eps) and [e["start"] for e in eps] == sorted(e["start"] for e in eps)


def test_a_long_episode_is_cut_into_chunks_with_their_own_opener(fresh_db):
    for i in range(23):
        _turn(f"step {i}", f"done {i}", (60 - i) * 60)       # one turn a minute, no silence anywhere
    eps = memapi.day_ledger(skip_newest=0)
    assert [e["turns"] for e in eps] == [10, 10, 3]
    assert [e["u"] for e in eps] == ["step 0", "step 10", "step 20"]
    assert max(e["turns"] for e in eps) <= memprompt.reads.EPISODE_MAX_TURNS


def test_the_day_is_rendered_for_the_live_tail_with_its_stats(fresh_db):
    h = 3600
    _turn("find me a song by the artist from that show", "That would be the lead singer, here it is", 3 * h)
    _turn("louder", "Done", 3 * h - 60)
    _live_thread(5)
    _block, _op, stats = memapi.compose_state(mission_fallback="m")
    day = memapi.day_block()
    assert day.startswith("HOY, EN ESQUEMA")
    assert "find me a song by the artist from that show" in day and "That would be the lead singer" in day
    assert "live complaint" not in day, "what the live window holds is not repeated in the day"
    assert "recall" in day, "the header points the model at recall instead of «I have no access»"
    assert "HOY, EN ESQUEMA" not in _block, "the day is read at the tail of the prompt, not in the cached state"
    assert stats["day_count"] == 1 and stats["day_chars"] > 0
    from nucleo.turn.prompt import live_state as _live
    tail = _live.live_state()
    assert "HOY, EN ESQUEMA" in tail and "find me a song by the artist from that show" in tail


def test_the_days_budget_drops_the_oldest_episode_first(fresh_db):
    h = 3600
    for k in range(10):                                     # ten episodes of three turns, an hour apart, oldest first
        _turn(f"episode {k} opener " + "x" * 120, f"episode {k} reply " + "y" * 140, (11 - k) * h)
        _turn(f"episode {k} more", f"episode {k} again " + "y" * 60, (11 - k) * h - 60)
        _turn(f"episode {k} last", f"episode {k} ending " + "z" * 90, (11 - k) * h - 120)
    _live_thread(5)
    kept = memapi.day_ledger()                              # the ledger itself keeps the newest `max_episodes`
    assert [e["u"][:9] for e in kept] == [f"episode {k}" for k in range(2, 10)]
    _block, _op, stats = memapi.compose_state(mission_fallback="m")
    block = memapi.day_block()
    assert stats["day_chars"] <= memcompose._DAY_MAX_CHARS
    assert 0 < stats["day_count"] < len(kept), "the budget bites: fewer lines than episodes kept"
    assert "episode 9 opener" in block, "the most recent episode is what he means: it stays"
    assert "episode 2 opener" not in block, "the oldest episode is the one the budget drops"


def test_with_only_the_live_thread_the_day_is_absent(fresh_db):
    _live_thread(5)
    _block, _op, stats = memapi.compose_state(mission_fallback="m")
    assert memapi.day_block() == ""
    assert stats["day_count"] == 0 and stats["day_chars"] == 0


def test_a_busy_evening_fits_the_mornings_day(fresh_db):
    """Seven ordinary episodes all reach the prompt: 1400 characters held four, and the one dropped first was the
    one he meant (measured 2026-11-09)."""
    h = 3600
    for k in range(7):
        _turn(f"episode {k}: find me something to listen to by the singer from that series, the second season",
              f"episode {k}: here is a song by the lead singer of that series, playing it on the music card",
              (9 - k) * h)
    _live_thread(5)
    _block, _op, stats = memapi.compose_state(mission_fallback="m")
    block = memapi.day_block()
    assert stats["day_count"] == 7, stats
    assert all(f"episode {k}: find me" in block for k in range(7))
    assert stats["day_chars"] <= memcompose._DAY_MAX_CHARS

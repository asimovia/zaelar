"""While something he asked for is being worked on and nobody is talking, he is told it goes on (V2-935).

Measured on his engine (2026-11-18): an errand ran six minutes and he heard nothing of it — «you don't even say one
moment, or that you are on it». The pulse now says a short worded line after a silence drawn at random between
`MIN_S` and `MAX_S`, a new draw every time somebody speaks; it names the step the errand reported; it is his to turn
off with a rule of his own (a `voice` row, the genesis knob `still_working_lines`); and a line that could not be said
is dropped — never pushed to his phone, never owed and said when the errand is long over.
"""
from __future__ import annotations

import asyncio

import pytest

import rules
from memory import db as memdb
from nucleo import style_policy
from nucleo.pulse import notices, still_on_it

RUNS = {"id": "2", "uid": "b0-2", "title": "Delete the groups «Book club» and «Shopping list»", "goal": "delete them",
        "phase": "looking for the two groups", "status": "running", "age_s": 300, "waiting_on": "", "paused": False}
NOW = 10_000.0


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    rules._reset_for_tests()
    w = {"last": NOW - 100.0, "voice": True, "he_speaks": False, "we_speak": False, "said": [], "kw": []}
    monkeypatch.setattr(still_on_it, "last_said_at", lambda: w["last"])
    monkeypatch.setattr(still_on_it, "_draw", lambda: 20.0)
    from voice import proactive
    monkeypatch.setattr(proactive, "has_voice", lambda: w["voice"])
    monkeypatch.setattr(proactive, "user_speaking", lambda: w["he_speaks"])
    monkeypatch.setattr(proactive, "bot_speaking", lambda: w["we_speak"])
    monkeypatch.setattr(proactive, "hushed", lambda: False)

    async def spoken(title, text, **kw):
        w["said"].append(text)
        w["kw"].append(kw)
        return w["voice"]
    monkeypatch.setattr(proactive, "notify", spoken)
    still_on_it._state.update(anchor=0.0, wait=0.0)
    yield w
    rules._reset_for_tests()
    memdb.reset_db()


def _say(key, **kw):
    return {"still_on_it": "Still on it."}.get(key, "")


def _beat(sessions, now=NOW):
    return asyncio.run(still_on_it.beat(sessions, now, _say))


def test_only_an_errand_being_worked_on_counts(world):
    waits = {**RUNS, "id": "3", "waiting_on": "user"}
    queued = {**RUNS, "id": "4", "status": "queued"}
    paused = {**RUNS, "id": "5", "paused": True}
    assert [s["id"] for s in still_on_it.running([RUNS, waits, queued, paused])] == ["2"]
    assert _beat([waits, queued, paused]) is False and world["said"] == [], "nothing runs: nothing to say"


def test_after_the_drawn_silence_he_hears_one_short_line_about_what_he_asked_for(world):
    world["last"] = NOW - 19.0
    assert _beat([RUNS]) is False, "19 s of silence, 20 drawn: not yet"
    world["last"] = NOW - 21.0
    assert _beat([RUNS]) is True
    assert world["said"] == ["Still on it."], "the suite's wording double says the language's own line"
    assert world["kw"][0].get("opens_window") is False, "it asks him nothing"
    assert world["kw"][0].get("task_id") == "b0-2", "the line belongs to its row"


def test_the_fact_names_the_step_the_errand_reported(world, monkeypatch):
    from nucleo import wording
    got = {}
    monkeypatch.setattr(wording, "word", lambda fact, **kw: got.update(fact=fact, **kw) or "x")
    still_on_it.line(RUNS, _say)
    assert "looking for the two groups" in got["fact"] and got["about"].startswith("Delete the groups")
    still_on_it.line({**RUNS, "phase": ""}, _say)
    assert "Where it is right now" not in got["fact"], "no step reported: none invented"
    assert got["fallback"] == "Still on it." and got["examples"] == ("Still on it.",)


def test_a_new_wait_is_drawn_every_time_somebody_speaks(world, monkeypatch):
    draws = iter([8.0, 35.0])
    monkeypatch.setattr(still_on_it, "_draw", lambda: next(draws))
    world["last"] = NOW - 10.0
    assert still_on_it.due([RUNS], NOW) is RUNS, "8 s drawn, 10 s quiet"
    world["last"] = NOW + 1.0                                   # he said something: the clock starts again
    assert still_on_it.due([RUNS], NOW + 11.0) is None, "35 s drawn now, 10 s quiet"
    assert still_on_it.MIN_S == 5.0 and still_on_it.MAX_S == 40.0
    assert all(still_on_it.MIN_S <= still_on_it.random.uniform(still_on_it.MIN_S, still_on_it.MAX_S) <= still_on_it.MAX_S
               for _ in range(50))


def test_an_errand_just_born_is_not_announced_before_its_own_silence(world):
    world["last"] = NOW - 500.0                                 # nobody spoke for a long while…
    assert still_on_it.due([{**RUNS, "age_s": 3}], NOW) is None, "…but the errand started 3 s ago"


@pytest.mark.parametrize("flag", ["he_speaks", "we_speak"])
def test_it_never_talks_over_anybody(world, flag):
    world[flag] = True
    assert _beat([RUNS]) is False and world["said"] == []


def test_with_no_voice_session_nothing_is_said_or_painted(world):
    world["voice"] = False
    assert _beat([RUNS]) is False and world["said"] == []


def test_a_line_that_could_not_be_said_is_dropped_never_pushed_nor_owed(world, monkeypatch):
    pushed = []
    monkeypatch.setattr(notices, "push", lambda row: pushed.append(row) or 1)
    world["voice"] = False
    got = asyncio.run(notices.notify("zaelar", "Still on it.", key="still:b0-2:1", task_id="b0-2", kind="info",
                                     ephemeral=True, opens_window=False))
    assert got["state"] == "dropped" and pushed == []
    assert notices.by_key("still:b0-2:1")["state"] == "dropped", "not owed: nothing retries it later"
    owed = asyncio.run(notices.notify("zaelar", "The report is ready.", key="k2", kind="info"))
    assert owed["state"] in ("pushed", "owed"), "an ordinary notice still reaches him"


def test_the_pulse_asks_on_every_tick():
    import inspect

    from nucleo.pulse import workers
    assert "still_on_it.beat(sessions, now, self._say)" in inspect.getsource(workers.WorkersPulse._supervise_workers)

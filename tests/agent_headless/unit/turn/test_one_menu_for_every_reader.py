"""One menu for every reader: an errand is its CARD, said once (V2-878 §2, nodes 2.1673, 2.1674 and 2.1675).

The errand had four names in four places — the worker's title cut at 60 on Flash's line, `goal[:160]` in the flow
judge's menu, the first three goals by start order in the brief's escalate question, and nothing at all in
`errand_target`, which was asked only while a worker ran (a parked or a just-finished errand could not be its answer).
Now every reader gets the same card — his words, its state, when he last named it (`named_errand.card_line`) — the
brief asks `errand_target` and the stop with ANY open errand, the escalate question carries the three he named last,
Flash's line carries one name per errand, and the recall's conversation lane skips the turns the window really holds.
"""
from __future__ import annotations

import time

import pytest

from nucleo import dispatch
from nucleo.request import append
from nucleo.turn import brief as tb
from nucleo.errands import named as named_errand
from nucleo.turn.prompt import live_tasks, recall

NOW = int(time.time())
CARDS = {
    "es": [{"id": "p1", "request": "Buscar vuelos baratos", "heard": "búscame un vuelo a Roma para el puente, que no pase de 150",
            "parked": True, "state": "waiting", "last_mention_ts": NOW - 600},
           {"id": "e1", "request": "Comparar monitores", "heard": "compárame monitores de 27 pulgadas 4K",
            "ended": True, "state": "done", "last_mention_ts": NOW - 60}],
    "en": [{"id": "p1", "request": "Find cheap flights", "heard": "find me a flight to Rome for the long weekend, under 150",
            "parked": True, "state": "waiting", "last_mention_ts": NOW - 600},
           {"id": "e1", "request": "Compare monitors", "heard": "compare 27 inch 4K monitors for me",
            "ended": True, "state": "done", "last_mention_ts": NOW - 60}],
}
SAID = {"es": "y del vuelo, mejor el viernes", "en": "and the flight, Friday is better"}


@pytest.fixture(params=["es", "en"])
def lang(request):
    return request.param


@pytest.fixture
def pool(monkeypatch, lang):
    cards = [dict(c) for c in CARDS[lang]]
    monkeypatch.setattr(named_errand, "known", lambda with_finished=False: [dict(c) for c in cards])
    return cards


def test_the_judge_and_errand_target_read_the_cards_of_a_parked_and_an_ended_errand(pool, lang, monkeypatch):
    sent = {}
    from nucleo.memory_agent.processor import llm
    monkeypatch.setattr(llm, "chat_sync", lambda key, system, user, **k: sent.update(user=user) or '{"about": 1}')
    assert append.about_a_live_errand(SAID[lang], [("p1", "x"), ("e1", "y")]) == "p1"
    for c in pool:
        assert c["heard"][:40] in sent["user"], "the judge's menu does not carry his words"
    assert "waiting for his answer" in sent["user"] and "finished" in sent["user"], "the menu does not say the state"
    assert "x" not in sent["user"].split("\n")[1].split("·")[0], "the goal rode beside the card"

    qs = tb.build(SAID[lang], has_workers=False, threads=pool)       # no worker running: a parked and an ended one
    target = qs.get("errand_target")
    assert target, "errand_target is asked only while a worker runs"
    desc = target["criteria"]["running_errand"]
    assert all(c["heard"][:40] in desc for c in pool) and "waiting for his answer" in desc
    assert set(target["criteria"]) == {"running_errand", "cluster_peer", "cluster_objective", "none"}, \
        "the choices every arm reads changed"
    assert "stop_errand" not in qs, "the stop (it ACTS: it kills a worker) is asked with no worker running"
    assert not tb.build(SAID[lang], has_workers=False, threads=[]).get("errand_target"), "asked with nothing open"


def test_the_escalate_question_carries_the_three_he_named_last(pool, lang):
    many = pool + [{"id": f"o{i}", "request": f"old errand {i}", "heard": f"old errand number {i}", "state": "running",
                    "last_mention_ts": NOW - 5000 - i} for i in range(3)]
    instr = tb.build(SAID[lang], has_workers=True, threads=many)["escalate_or_inline"]["instructions"]
    assert pool[1]["heard"][:30] in instr and pool[0]["heard"][:30] in instr and "old errand number 0" in instr
    assert "old errand number 1" not in instr, "more than three, or not the ones he named last"
    assert instr.index(pool[1]["heard"][:30]) < instr.index(pool[0]["heard"][:30]), "not ordered by his last mention"


@pytest.fixture
def live(monkeypatch):
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


def test_the_recall_lane_skips_the_turns_the_window_really_holds(monkeypatch):
    import asyncio
    from nucleo.turn import recall_budget
    seeded = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
              {"role": "user", "content": "c"}, {"role": "assistant", "content": "d"},
              {"role": "user", "content": "e"}]
    assert recall.live_turns(seeded) == 3
    assert recall.live_turns([{"role": "user", "content": str(i)} for i in range(12)]) == recall.LIVE_WINDOW_TURNS
    seen = []
    from memory import api as memory
    monkeypatch.setattr(memory, "conversation", lambda **k: seen.append(k["skip_newest"]) or [])
    monkeypatch.setattr(memory, "query", lambda *a, **k: [], raising=False)
    asyncio.run(recall_budget.compose("the artist I asked about", {"live_turns": recall.live_turns(seeded)}))
    assert seen and set(seen) == {3}, f"the lane skipped {seen} turns, the window holds 3"
    src = __import__("inspect").getsource(__import__("voice.engine.llm.providers.turn_prompt", fromlist=["x"]))
    assert 'timings["live_turns"] = _recall_lane.live_turns(brain._window' in src, "the voice turn does not hand its window down"


@pytest.mark.parametrize("said, parts", [
    ("búscame un monitor barato, hazme un informe de coches eléctricos y móntame un juego de plataformas",
     ["buscar un monitor barato de segunda mano", "informe sobre coches eléctricos", "juego de plataformas"]),
    ("find me a cheap monitor, write a report on electric cars and build me a platform game",
     ["find a cheap second-hand monitor", "report on electric cars", "platform game"])])
def test_an_errand_that_is_one_part_of_a_sentence_is_judged_by_its_own_request(said, parts, monkeypatch):
    """Measured (three-tasks-at-once, V2-878 §2 bank): the card of each of three errands carried the WHOLE sentence; the
    judge's menu showed it, and the game's escalation was folded into the report, then every later turn routed there."""
    cards = [{"id": str(i + 1), "request": r, "heard": said, "part": i, "state": "running"} for i, r in enumerate(parts)]
    monkeypatch.setattr(named_errand, "known", lambda with_finished=False: [dict(c) for c in cards])
    lines = append._menu([(c["id"], c["request"]) for c in cards])
    for line, mine, others in ((lines[i], parts[i], parts[:i] + parts[i + 1:]) for i in range(3)):
        assert mine in line and said not in line and not any(o in line for o in others), line
    one = named_errand.card_line({"id": "9", "request": "x", "heard": said, "state": "running"})
    assert said[:40] in one, "a single errand's app lost his words"

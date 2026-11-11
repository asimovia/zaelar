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
from nucleo.turn import named_errand
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
    assert "stop_errand" in qs, "the stop is not asked with an errand open"
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


@pytest.mark.parametrize("heard", ["búscame tres monitores de 27 pulgadas 4K por menos de 400",
                                   "find me three 27 inch 4K monitors under 400 bucks"])
def test_the_same_errand_appears_once_in_the_prompt(live, heard):
    from nucleo.turn.prompt import live_state as P
    rec = dispatch.SessionRecord(task_id="t1", goal="Buscar monitores de 27 pulgadas con resolución 4K (UHD) con precio",
                                 kind="web", heard=heard)
    rec.status = "running"
    rec.started = rec.last_event_at = time.time() - 30
    dispatch._SESSIONS["t1"] = rec
    prompt = P.live_state()
    assert prompt.count(heard[:50]) == 1, "his words said twice"
    assert "Buscar monitores de 27 pulgadas con resolución" not in prompt, "the errand said under a second name"
    assert "Si el operador pregunta" not in prompt and "NUNCA repitas" not in prompt, "the imperative paragraph is back"


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


@pytest.mark.parametrize("heard", ["búscame un monitor bueno para trabajar, que no sea carísimo",
                                   "find me a good monitor for work that isn't too pricey"])
def test_the_whole_prompt_says_a_live_errand_once_and_the_state_block_does_not_move_with_its_phase(
        live, tmp_path, monkeypatch, heard):
    """The memory STATE block rendered the live session too (`PROCESOS DE FONDO en marcha ahora: [1] «…» — fase: …`),
    in the middle of the shared prompt: the errand was said twice, and its changing phase broke the prompt cache for
    everything after it every turn (measured on cheapest-monitor: the cache hit stuck at ~6.4k of ~15k tokens)."""
    from memory import api as memapi, db as memdb
    from nucleo.flash import memory_cache
    from nucleo.turn.prompt import builder
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memory_cache.reset()
    try:
        rec = dispatch.SessionRecord(task_id="1", goal="Buscar monitores para trabajar baratos", kind="web", heard=heard)
        rec.status, rec.phase = "running", "comparando precios"
        rec.started = rec.last_event_at = time.time() - 30
        dispatch._SESSIONS["1"] = rec
        memapi.set_state({"sessions": [{"id": "1", "goal": rec.goal, "phase": "comparando precios"}]})
        system, _ = builder.build_flash_system()
        assert system.count(heard[:40]) == 1, "the live errand said more than once in the prompt"
        assert "Buscar monitores para trabajar baratos" not in system, "the errand said under a second name"
        assert "[1] «" in system, "the running-errands line lost the id an order to it names"
        memapi.set_state({"sessions": [{"id": "1", "goal": rec.goal, "phase": "abriendo fichas"}]})
        memory_cache.reset()
        state_a = memapi.compose_state()
        memapi.set_state({"sessions": [{"id": "1", "goal": rec.goal, "phase": "verificando precios"}]})
        memory_cache.reset()
        assert memapi.compose_state() == state_a, "the shared state block moves with a worker's phase"
    finally:
        memory_cache.reset()
        memdb.reset_db()


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
    assert said[:40] in one, "a single errand's card lost his words"

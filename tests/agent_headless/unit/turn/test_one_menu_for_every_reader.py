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
from nucleo.errands import named as named_errand

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


@pytest.fixture
def live(monkeypatch):
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


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

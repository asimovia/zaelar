"""An errand's outcome is judged on what it DELIVERED: an empty result is not `met` (INI-071 B3, 2026-11-16).

Measured on the local engine: a search errand that found nothing closed `done/met` and left a result pill in memory. Its
end state was the one `navegador:search` declares — the query is on the page, the page changed, no wall — and searching
ALONE makes that true. The circuit read the card's state and called the errand delivered.

The class: what an errand promised to hand over is part of its ending, whatever its spec says. An errand whose surface
is a results sheet (a list, one item) promised ROWS; one that reported its finalists promised that many. Nothing kept
→ the ending is `unmet` with the reason, through the circuit's one retry rule, and the memory door — which only admits
a delivered verdict — writes nothing. A delivery that holds rows is judged by its spec exactly as before.

Variants in other domains and languages on purpose: flats (ES), a restaurant (EN), and a worker with no sheet that
reported it kept none of what it considered.
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from nucleo import circuit
from nucleo.circuit import spec as _spec
from nucleo.circuit import verdict as _verdict
from nucleo.circuit import verify as _verify
from nucleo.workers.session import SessionRecord

SEARCH_DONE = {"all": [{"widget": "navegador", "field": "rev", "expect": "changed"},
                       {"widget": "navegador", "field": "failed", "expect": "absent"}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    _spec.reset()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "w"))
    relaunched: list = []
    from nucleo.acts import errand as escalate
    monkeypatch.setattr(escalate, "escalate_to_slowbrain",
                        lambda req, context=None: relaunched.append((req, context or {})) or 901)
    monkeypatch.setattr(_verify, "check", lambda dw, now=None: True if dw else None)  # searching made the spec true
    yield relaunched
    _spec.reset()
    memdb.reset_db()


def _sheet(sheet: str, rows: int) -> None:
    from widgets.results import data as _d
    data = _d._empty()
    data["items"] = [{"title": f"Found {i}", "url": f"https://example.test/{sheet}/{i}"} for i in range(rows)]
    _d._save(data, sheet)


def _errand(goal: str, uid: str, *, surface: str = "lista", rows: int | None = 0, **kw) -> SessionRecord:
    rec = SessionRecord(task_id=uid[-2:], goal=goal, kind="research", uid=uid, status="done", ok=True,
                        surface=surface, sheet=uid if surface in ("lista", "item") else "")
    rec.done_when = dict(SEARCH_DONE)
    rec.result_summary = "Here is what I found."
    for k, v in kw.items():
        setattr(rec, k, v)
    if rec.sheet and rows is not None:
        _sheet(rec.sheet, rows)
    return rec


CASES = [("busca pisos de dos habitaciones en alquiler en Valencia por menos de 900 €", "u-flats-es", "lista", {}),
         ("find me a vegan restaurant open after midnight near the harbour", "u-food-en", "item", {}),
         ("compare second-hand road bikes under £400 and keep the best", "u-bikes-en", "voz",
          {"considered": 23, "kept": 0})]


@pytest.mark.parametrize("goal,uid,surface,kw", CASES)
def test_an_errand_that_delivered_nothing_is_not_met_and_leaves_no_memory(world, goal, uid, surface, kw):
    rec = _errand(goal, uid, surface=surface, **kw)
    v = circuit.close(rec, relay_cap=2)
    assert v != "met", "an errand that delivered nothing was judged fulfilled by the card's state"
    assert rec.verdict in ("unmet", "started"), rec.verdict          # unmet, or its one bounded relaunch
    assert not (_verdict.of(rec.verdict) and _verdict.of(rec.verdict).delivered), "the memory door would admit it"
    from nucleo.memory_agent import writer
    assert writer.admits(uid, rec.verdict, goal)[1], "a result pill would be written for an empty delivery"


def test_the_relaunch_carries_that_nothing_was_found(world):
    relaunched = world
    rec = _errand(CASES[0][0], "u-flats-retry")
    assert circuit.close(rec, relay_cap=2) == "started" and relaunched, "an empty delivery is a shortfall to iterate"
    assert "[ARNÉS]" in relaunched[0][0]


def test_with_no_try_left_it_says_it_could_not_and_is_not_delivered(world, monkeypatch):
    monkeypatch.setattr(circuit, "retries", lambda: 0)
    rec = _errand(CASES[1][0], "u-food-last")
    assert circuit.close(rec, relay_cap=2) == "unmet" and rec.ok is False
    assert rec.result_summary.startswith("No he podido dejarlo terminado")


@pytest.mark.parametrize("goal,uid,surface,kw", CASES[:2])
def test_a_delivery_that_holds_rows_is_judged_by_its_spec_as_before(world, goal, uid, surface, kw):
    rec = _errand(goal, uid, surface=surface, rows=3)
    assert circuit.close(rec, relay_cap=2) == "met"


def test_a_worker_with_no_sheet_and_no_count_is_judged_by_its_spec_as_before(world):
    rec = _errand("tell me tomorrow's tide times in Cádiz", "u-tide-es", surface="voz")
    assert circuit.close(rec, relay_cap=2) == "met"


# ── what emptiness does NOT say (the audit of B3, 2026-11-17) ────────────────────────────────────────────────

def test_a_sheet_nobody_declared_says_nothing_of_an_errand_that_acts(world):
    """A web errand with no declared surface gets a sheet from its KIND (`surfaces._BY_KIND`), and one that acts — a
    booking, an auto-resumed form — never writes a row on it. Sealed through the dispatcher's own door (`set_once`)."""
    from nucleo import surfaces
    rec = SessionRecord(task_id="b1", goal="reserva mesa para dos el viernes a las nueve", kind="web",
                        uid="u-book-es", status="done", ok=True, sheet="u-book-es")
    assert surfaces.set_once(rec, None) == surfaces.LIST and surfaces.guessed(rec)
    rec.done_when, rec.result_summary = dict(SEARCH_DONE), "Reserved."
    _sheet(rec.sheet, 0)
    assert circuit.close(rec, relay_cap=2) == "met" and not world, "a finished act was relaunched for an empty sheet"
    relay = SessionRecord(task_id="b2", goal=rec.goal, kind="web", uid="u-book-es", status="done", ok=True,
                          sheet="u-book-es")
    assert surfaces.set_once(relay, rec.surface) == surfaces.LIST and surfaces.guessed(relay), \
        "a relay carries the sealed surface: it must still read as a guess"
    declared = SessionRecord(task_id="b3", goal="find flats", kind="web", uid="u-flats-declared", ok=True)
    surfaces.set_once(declared, "lista")
    assert not surfaces.guessed(declared)


def test_an_emptiness_the_breadth_judge_called_enough_is_the_answer(world):
    """«No flights that day» is an answer: the model that judged the breadth said the shortfall is legitimate, so the
    errand is neither relaunched nor told as not done."""
    rec = _errand("are there direct flights from Vigo to Oslo on Christmas Day", "u-flights-en")
    rec.breadth = {"judged": True, "enough": True, "short": True, "why": "No airline flies that route that day.",
                   "target": {"n_final": 3}, "progress": {"rows": 0}}
    assert circuit.close(rec, relay_cap=2) == "met" and not world
    rec2 = _errand("are there direct flights from Vigo to Oslo on Christmas Day", "u-flights-nj")
    rec2.breadth = {"judged": False, "enough": True, "short": True}          # the judge failed: not a verdict
    assert circuit.close(rec2, relay_cap=2) == "started"


def test_the_judges_own_gap_is_what_a_relaunch_carries(world):
    """The breadth judge said NOT enough and named the next step: that gap — and the brief to resume — is what the
    relaunch carries, not the bare «nothing was found»."""
    rec = _errand(CASES[0][0], "u-flats-gap")
    rec.breadth = {"judged": True, "enough": False, "short": True, "next": "try the two regional portals",
                   "target": {"min_candidates": 20, "n_final": 5}, "progress": {"explored": 4, "rows": 0}}
    assert circuit.close(rec, relay_cap=2) == "started"
    req, ctx = world[0]
    assert "try the two regional portals" in req and "resume" in ctx


def test_a_worker_that_did_not_say_it_delivered_is_told_by_its_own_reason(world):
    rec = _errand(CASES[0][0], "u-flats-died", ok=False)
    rec.done_when = {}
    assert circuit.close(rec, relay_cap=2) == "undeclared" and not world, "a failed ending was relaunched as an empty search"

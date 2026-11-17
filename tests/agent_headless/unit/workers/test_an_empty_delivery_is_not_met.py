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

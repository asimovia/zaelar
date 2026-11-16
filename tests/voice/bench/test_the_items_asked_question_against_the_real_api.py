"""The `items_asked` question against the real decision model — opt-in, same rules as its sibling bench.

A text session (2026-11-16): «Also add: Tuesday 9am team standup, Wednesday 3pm coffee with Sam, Thursday 6pm piano
lesson, and Sunday 11am brunch with the family.» → one call, one appointment, «Done.». How many NEW ENTRIES his words
name is `nucleo/turn/items_asked.py`'s question. This bench holds the two sides of its line: several entries named
read «several» at the veto floor, and one entry with many details, a bulk change of what exists, a show, a play or
two different acts never do.

    ZAELAR_JEV_BENCH=1 ZAELAR_TEST_JEV_LIVE=1 ./.venv/bin/python -m pytest -q -s tests/voice/bench/test_the_items_asked_question_against_the_real_api.py

The metric is the sibling's: wrong-and-confident, target zero — «several» at or above `verdicts.VETO` where one entry
(or none) was named, or under it where several were. Measured 2026-11-16, 2 of 2 each: 0 wrong at the floor; the
closest calls were a list with its contents (several 0.86-0.88) and «add milk, eggs and bread to the list» (0.96).
"""
from __future__ import annotations

import json
import os
import pathlib
import time

import pytest

BENCH = os.getenv("ZAELAR_JEV_BENCH", "").strip() not in ("", "0", "no", "false")
pytestmark = pytest.mark.skipif(not BENCH, reason="opt-in: set ZAELAR_JEV_BENCH=1 (spends money)")

REPORTS = pathlib.Path(__file__).resolve().parents[3] / "tests" / "runs" / "jev-bench"

#: (phrase, what the mouth must NOT be told). `one` = a close that ends it: «several» must stay under the veto floor.
#: `several` = two results of their own: «several» must reach the floor, or the F4 line is lost.
#: (phrase, what he named). `several` must reach the veto floor or the line is lost; `one` must stay under it.
CASES = [
    ("Also add: Tuesday 9am team standup, Wednesday 3pm coffee with Sam, Thursday 6pm piano lesson, and Sunday "
     "11am brunch with the family.", "several"),
    ("Remind me tomorrow at 8am to water the plants, and on Friday at 5pm to call the bank.", "several"),
    ("Apúntame el dentista el lunes a las 10 y la comida con Marta el martes a las 2", "several"),
    ("pon una alarma a las 7 y otra a las 7 y media", "several"),
    ("Make me a shopping list: oat milk, avocados, sourdough bread, eggs, coffee beans and spinach.", "several"),
    ("hazme una lista de la compra con leche, huevos y pan", "several"),
    ("Add coffee with Sam on Wednesday at 3pm.", "one"),
    ("Add a piano lesson on Thursday at 6pm at the music school with Ms. Rowan, and invite Quinn", "one"),
    ("create a list called Trip to Rome", "one"),
    ("recuérdame mañana llamar a mamá", "one"),
    ("mueve la cita del dentista al jueves a las 5 y avisa a Marta", "one"),
    ("cancel all my meetings on Friday", "one"),
    ("mark the first three tasks as done", "one"),
    ("delete the dentist and the lunch from my calendar", "one"),
    ("stop the music and show me the calendar", "one"),
    ("What's on my calendar tomorrow and on Friday?", "one"),
    ("schedule a weekly piano lesson every Tuesday at 6pm until June", "one"),
]
REPEAT = 3


@pytest.fixture(autouse=True)
def _never_the_operators_timeline(monkeypatch):
    sink: list = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: sink.append((a, k)))
    real = pathlib.Path(__file__).resolve().parents[3] / ".meshkore" / "logs" / "timeline-latest.jsonl"
    before = real.stat().st_size if real.exists() else 0
    yield sink
    # the operator's LIVE engine writes this file too (its watchdog alerts landed 394 bytes during one run): the
    # check is on what the bench itself would have written, never on the byte count
    tail = b""
    if real.exists() and real.stat().st_size > before:
        with real.open("rb") as fh:
            fh.seek(before)
            tail = fh.read()
    assert b"bench-items-asked" not in tail, "the bench wrote its verdicts into the operator's real timeline"


def test_several_entries_reach_the_floor_and_one_entry_never_does(_never_the_operators_timeline):
    sink = _never_the_operators_timeline
    from nucleo import jev
    from nucleo.turn import items_asked as A, verdicts
    assert jev.enabled(), "no key: the bench cannot measure anything"
    q = A.question()
    rows, wrong = [], []
    for phrase, want in CASES:
        for _ in range(REPEAT):
            t0 = time.monotonic()
            v = jev.choose_sync(A.KEY, phrase, instructions=q["instructions"], criteria=q["criteria"],
                                question_id="bench-items-asked") or {}
            got, conf = str(v.get("choice") or ""), float(v.get("confidence") or 0.0)
            assert got, f"no verdict came back: {(sink[-1][1].get('extra') or {}) if sink else 'nothing emitted'}"
            row = {"phrase": phrase, "want": want, "got": got, "conf": round(conf, 2),
                   "ms": int((time.monotonic() - t0) * 1000)}
            rows.append(row)
            # the mouth reads «several» only at the veto floor (`items_asked.several`)
            said = got == A.SEVERAL and conf >= verdicts.VETO
            if (want == "one" and said) or (want == "several" and not said):
                wrong.append(row)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{time.strftime('%Y%m%d-%H%M%S')}-items-asked.json"
    path.write_text(json.dumps({"question": A.KEY, "rows": rows, "wrong": wrong, "criteria_measured": q},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[bench] items_asked → {len(rows)} verdicts, {len(wrong)} wrong at the floor\n[bench] archived: {path}")
    for r in rows:
        print(f"    {r['phrase'][:60]!r:62} → {r['got']:8} ({r['conf']:.2f}) want {r['want']}")
    assert not wrong, wrong

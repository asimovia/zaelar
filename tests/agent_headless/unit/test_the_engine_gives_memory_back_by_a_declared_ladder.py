"""The engine gives memory back one declared rung at a time, and takes it back in reverse (V2-891, node 3.193).

Measured on the operator's machine: «shedding load (nothing to pause)» 279 times in one session while the voice went
deaf — the watchdog had ONE lever (pause the newest worker while another runs) and, with no worker running, nothing.
The pressure was the host's (a 31.7 GB local model resident), not ours, and the engine still had things to give back.

  (a) under pressure the rungs engage in the DECLARED order, one per step, whatever the cause — `cause` says whose
      memory it is (`engine` over our budgets, `machine` within them) and the ladder descends for both;
  (b) recovered with margin (free ≥ floor × `shed_recover_ratio`) they release in REVERSE order, one per step;
      between the floor and the margin nothing moves (no flapping on the floor);
  (c) the order is data (`shed_ladder` in `config/resources.default.json`), and every declared rung has a hand in
      the body (`nucleo/pulse/shed_actuators.py`);
  (d) the hands move what they name and undo only their own: the hold is the ladder's own source, released by the
      ladder; the background hold stops the ticks and lets them run again.

Disarms (each seen red): `self.engaged.pop(0)` instead of `pop()` in `Ladder.step` → (b); drop the `recovered()`
margin (release as soon as pressure ends) → (b) flaps; `return None` for `cause == "machine"` → (a).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from nucleo.pulse import shed_ladder as SL

FLOOR = 1000.0


def _r(free, cause="machine", lag=0.0):
    return {"free_mb": free, "floor_mb": FLOOR, "voice_lag_s": lag, "lag_bound_s": 0.5, "cause": cause}


def test_under_pressure_the_rungs_engage_in_the_declared_order_whoever_is_short():
    lad = SL.Ladder(rungs=("a", "b", "c"))
    acts = [lad.step(_r(500, cause="machine")) for _ in range(4)]
    assert [a["engage"] for a in acts[:3]] == ["a", "b", "c"]
    assert acts[3] is None, "every rung is down: nothing more to give"
    assert all(a["cause"] == "machine" for a in acts[:3])
    lad2 = SL.Ladder(rungs=("a", "b"))
    assert lad2.step(_r(500, cause="engine"))["cause"] == "engine"


def test_the_voices_own_lag_is_pressure_too():
    lad = SL.Ladder(rungs=("a",))
    assert lad.step(_r(5000, lag=0.8)) == {"engage": "a", "cause": "machine", "depth": 1}


def test_recovery_releases_in_reverse_and_only_with_margin():
    lad = SL.Ladder(rungs=("a", "b", "c"), recover_ratio=1.15)
    for _ in range(3):
        lad.step(_r(500))
    assert lad.step(_r(1100)) is None, "over the floor but under the margin: nothing moves"
    rel = [lad.step(_r(1200)) for _ in range(4)]
    assert [a["release"] for a in rel[:3]] == ["c", "b", "a"]
    assert rel[3] is None and lad.depth() == 0


def test_whose_memory_it_is():
    assert SL.cause(engine_mb=1500, engine_budget_mb=1200) == "engine"
    assert SL.cause(engine_mb=800, engine_budget_mb=1200) == "machine"


def test_the_order_is_data_and_every_rung_has_a_hand():
    root = Path(__file__).resolve().parents[3]
    declared = json.loads((root / "config/resources.default.json").read_text())
    assert declared["shed_ladder"][0] == "hold_workers", "the cheapest, fully reversible rung goes first"
    assert SL.from_policy(declared).rungs == tuple(declared["shed_ladder"])
    assert SL.from_policy({}).rungs == (), "a ladder nobody declared gives nothing back"
    from nucleo.pulse import shed_actuators as A
    src = (root / "nucleo/pulse/shed_actuators.py").read_text()
    for rung in declared["shed_ladder"]:
        assert f'"{rung}"' in src, f"the rung {rung!r} is declared and nothing in the body moves it"
    assert A._engage("no_such_rung") == "unknown rung"


def test_the_hands_move_what_they_name_and_undo_only_their_own(monkeypatch):
    from nucleo.pulse import shed_actuators as A
    from nucleo.workers import envelope
    from widgets import background
    envelope._sheds.clear()
    envelope.shed(60, "voice_audio")
    assert A._engage("hold_workers") == "held" and "ladder" in envelope._sheds
    assert A._release("hold_workers") == "released"
    assert "ladder" not in envelope._sheds and "voice_audio" in envelope._sheds, "it released another source's hold"
    envelope._sheds.clear()
    A._engage("pause_background")
    assert background.held()
    ran = []
    monkeypatch.setattr(background, "_call_tick", lambda wid: ran.append(wid))
    asyncio.run(background._tick_once_paced("agenda", "passive"))
    assert ran == [], "a held background still ticked"
    A._release("pause_background")
    assert not background.held()
    asyncio.run(background._tick_once_paced("agenda", "passive"))
    assert ran == ["agenda"]


def test_one_beat_reads_moves_and_says(monkeypatch):
    from nucleo.pulse import shed_actuators as A
    A._L["ladder"] = SL.Ladder(rungs=("trim_caches",))
    monkeypatch.setattr(A, "reading", lambda: {**_r(100), "engine_mb": 900.0, "budget_mb": 1200.0})
    said = []
    act = A.step(lambda label, text, extra=None: said.append((label, text, extra)))
    assert act["engage"] == "trim_caches" and act["did"].startswith("gc ")
    assert said and said[0][0] == "shed_ladder" and said[0][2]["cause"] == "machine"
    A._L["ladder"] = None

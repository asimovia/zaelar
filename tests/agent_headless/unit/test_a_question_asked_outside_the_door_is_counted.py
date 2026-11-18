"""V2-851 F2c — the door is the one reader of «which person / which channel / missing fact».

A turn that ends on our own question while the brief names a card whose acts leave the machine, and no call reached
any door, asked OUTSIDE the door: nothing retained, no durable question. It is counted as one `ask_outside_door`
event (never repaired — no second model pass), and the send's declaration tells the model the door asks.
"""
from __future__ import annotations

from tests.voice_turn_source import read as _vts_read

import ast
import json
from pathlib import Path

import pytest

from nucleo.request import ask_outside_door as aod
from nucleo.turn import verdicts

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def card(monkeypatch):
    """The brief names card `wid`; `lean` is the act it reads there at ANY confidence ("" = none read)."""
    def _set(wid, lean="send_to"):
        def _read(h, key, fb, min_confidence=None):
            if key == "catalog_widget":
                return wid, {"confidence": .9}
            if key == "screen_action" and lean and not min_confidence:
                return f"{wid}:{lean}", {"confidence": .43}
            return fb, None
        monkeypatch.setattr(verdicts, "read", _read)
    return _set


def _measure(reply, *, did_act=False, which=False):
    got = []
    ok = aod.measure(object(), reply, did_act=did_act, asked_which=which,
                     emit=lambda kind, label, text="", role="", extra=None: got.append((kind, extra)))
    return ok, got


def test_a_question_about_a_send_that_reached_no_door_is_counted(card):
    card("mensajeria")
    ok, got = _measure("¿A qué Raquel: Gómez o Martín?")
    assert ok and got[0][0] == aod.KIND and got[0][1]["widget"] == "mensajeria" and "send_to" in got[0][1]["leaves"]


def test_a_turn_that_reached_a_door_or_did_not_ask_is_not(card):
    card("mensajeria")
    assert _measure("¿A qué Raquel?", did_act=True) == (False, [])
    assert _measure("Se lo mando ahora.") == (False, [])
    assert _measure("Raquel Gómez o Raquel Martín.", which=True)[0], "the directory says it asked which person"


@pytest.mark.parametrize("reply", ["Vale, olvidado. ¿Y qué estabas viendo?", "Sure, forgotten. What were you watching?"])
def test_a_card_he_only_talked_about_is_no_door_and_our_question_is_talk(card, reply):
    """11:16:12 on his engine (2026-11-18): «I was watching TV, forget that message» named the messaging card and NO act
    of it; our small-talk question became a row waiting on his answer, his next order was routed into it and a worker
    started with the TV line as its brief. A card with no act read is a subject, never a door."""
    card("mensajeria", lean="")
    assert _measure(reply) == (False, []), "no act was read: nothing is counted, so nothing is made a row"
    assert _measure("Raquel Gómez o Raquel Martín.", which=True)[0], "the directory's «which person» still is one"


def test_disarm_a_card_named_with_no_act_would_open_a_row(card, monkeypatch):
    card("mensajeria", lean="")
    monkeypatch.setattr(aod, "_reads_an_act", lambda *a, **k: True)
    assert _measure("Vale, olvidado. ¿Y qué estabas viendo?")[0], "the reading of an act is what keeps talk from being a task"


def test_a_card_whose_acts_never_leave_is_not_a_door_question(card):
    card("none")
    assert _measure("¿Qué quieres?") == (False, [])


def test_the_turn_end_measures_it_and_the_kind_has_a_family():
    src = _vts_read(ROOT / "nucleo/turn/pipeline_close.py")
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "measure" and getattr(n.func.value, "id", "") == "_aod"]
    assert calls and {k.arg for k in calls[0].keywords} >= {"did_act", "asked_which", "emit"}
    from voice import observer
    assert observer._CAT.get(aod.KIND) == "flash"


def test_the_send_declares_that_the_door_asks_which():
    spec = json.loads((ROOT / "widgets/mensajeria/manifest.json").read_text())["actions"]["send_to"]
    assert "PREGÚNTASELO" not in spec["usage"], "the declaration no longer tells the model to ask on its own"
    assert "el widget le pregunta" in spec["usage"]

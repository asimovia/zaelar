"""V2-851 F2c — the door is the one reader of «which person / which channel / missing fact».

A turn that ends on our own question while the brief names a card whose acts leave the machine, and no call reached
any door, asked OUTSIDE the door: nothing retained, no durable question. It is counted as one `ask_outside_door`
event (never repaired — no second model pass), and the send's declaration tells the model the door asks.
"""
from __future__ import annotations


import json
from pathlib import Path



ROOT = Path(__file__).resolve().parents[3]


def test_the_send_declares_that_the_door_asks_which():
    spec = json.loads((ROOT / "widgets/mensajeria/manifest.json").read_text())["actions"]["send_to"]
    assert "PREGÚNTASELO" not in spec["usage"], "the declaration no longer tells the model to ask on its own"
    assert "el widget le pregunta" in spec["usage"]

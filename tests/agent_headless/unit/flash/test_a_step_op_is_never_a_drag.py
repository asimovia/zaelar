"""A STEP op repeated is another step, never the previous turn's op dragged along (V2-795).

Measured live: «Johnny, pon la siguiente» ran `musica:next`; fifteen seconds later «pon la siguiente canción de la
lista» re-emitted the identical `next {}` and the anti-drag guard (`data_ops.is_context_bleed`) ate it as
context-bleed — an empty payload shares no words with any sentence, so its hatch could never open — and the turn
ended «No lo he hecho». Whether an action is a step is DECLARED by its card (`"repeatable": true`), read
generically; nothing here names an op.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from nucleo.flash import data_ops

ROOT = Path(__file__).resolve().parents[4]


#: What reached the guard live: the second half of the sentence, the part after the wake word and «pon la siguiente».
SAID = "canción de la lista."


def _last(wid, action, payload=None):
    return (wid, action, payload or {}, time.time() - 15)


def test_the_cards_declare_their_steps():
    for wid, steps in (("musica", {"next", "previous", "volume_up", "volume_down", "seek"}),
                       ("youtube", {"next", "previous", "volume_up", "volume_down"})):
        acts = json.loads((ROOT / f"widgets/{wid}/manifest.json").read_text(encoding="utf-8"))["actions"]
        assert {n for n, s in acts.items() if s.get("repeatable") is True} == steps, wid


def test_next_song_asked_twice_is_two_skips():
    assert not data_ops.is_context_bleed(_last("musica", "next"), "musica", "next", {}, SAID)


def test_another_cards_step_is_a_step_too():
    for action in ("next", "volume_up"):
        assert not data_ops.is_context_bleed(_last("youtube", action), "youtube", action, {}, "otra"), action


def test_a_write_repeated_unasked_is_still_a_drag():
    payload = {"title": "Dentista", "date": "2026-10-25", "time": "10:00"}
    assert data_ops.is_context_bleed(_last("agenda", "add_meeting", payload), "agenda", "add_meeting", payload,
                                     "borra el reloj")


def test_a_step_is_read_from_the_declaration_not_from_its_name(monkeypatch):
    from widgets import runtime
    real = runtime.get

    def without_flag(wid):
        m = real(wid)
        if wid != "musica" or not m:
            return m
        acts = {k: dict(v) for k, v in (m.get("actions") or {}).items()}
        acts["next"].pop("repeatable", None)
        return {**m, "actions": acts}
    monkeypatch.setattr(runtime, "get", without_flag)
    assert data_ops.is_context_bleed(_last("musica", "next"), "musica", "next", {}, SAID), \
        "undeclared, the same empty op 15 s later is read as a drag — the flag is what decides"

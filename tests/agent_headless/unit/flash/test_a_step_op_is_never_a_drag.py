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

from nucleo.acts import data_ops

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

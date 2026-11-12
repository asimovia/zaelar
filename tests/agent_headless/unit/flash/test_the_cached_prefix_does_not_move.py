"""V2-889 F1 — the part of the voice turn the provider caches is byte-identical from turn to turn.

Measured 2026-11-12 on the fast model: the provider caches the request as a PREFIX (system → tools → window). With the
clock, the screen and the memory inside the system message, 51 % of the prompt was cached; with those facts in a
second system message right before his line, 98-99 %. Naming a card used to reorder the catalogue rows and rewrite the
middle of the system message, which threw away everything after it, the ~6k tokens of tools included.
"""
from __future__ import annotations

import json
import subprocess
import sys

_SNIPPET = """
import json, sys
from tests.platform.turn_harness import Isolated
with Isolated("es"):
    from memory import api as memapi
    from nucleo.turn.prompt.builder import build_flash_system, split_state
    from nucleo.flash import router
    out = []
    for cards, text in (([], "hola"), (["agenda"], "pon música de jazz"), (["agenda", "youtube", "musica"],
                         "escríbele a Quinn por telegram"), (["contactos"], "¿qué tengo mañana en la agenda?")):
        memapi.set_state({"open_widgets": cards, "recent_widgets": ["mensajeria"]})
        stable, state = split_state(build_flash_system(timings={}, turn_text=text)[0])
        ctx = router.tool_context(has_workers=bool(cards), confirm_pending=len(cards) == 3)
        names = [t["function"]["name"] for t in router.tools(ctx)]
        gated = [n for n in names if n in router._SITUATIONAL]
        out.append({"stable": stable, "state": state, "names": names, "gated": gated})
print("OUT" + json.dumps(out))
"""


def _turns() -> list[dict]:
    r = subprocess.run([sys.executable, "-c", _SNIPPET], capture_output=True, text=True, timeout=120)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("OUT")), None)
    assert line, r.stderr[-2000:]
    return json.loads(line[3:])


def test_the_prefix_is_the_same_bytes_whatever_he_says_or_has_open():
    turns = _turns()
    assert len({t["stable"] for t in turns}) == 1, "the cached prefix changed between turns"
    assert all(t["state"].startswith("── ESTADO DE ESTE TURNO") for t in turns)
    # what moved is in the state: the cards in play this turn are named there, not in the catalogue rows
    assert "◀ EN PANTALLA" not in turns[0]["stable"]
    assert "agenda  ◀ EN PANTALLA" in turns[1]["state"]


def test_the_tools_offered_always_come_before_the_ones_state_gates():
    for t in _turns():
        names, gated = t["names"], set(t["gated"])
        first_gated = next((i for i, n in enumerate(names) if n in gated), len(names))
        assert all(n in gated for n in names[first_gated:]), names

"""V2-705 · ONE doctrine of ownership: a widget with a connector IS the source — written once, read by all.

Measured 2026-09-15 (session 878b0122). Three prompts said the opposite of the code, each in its own words:
the escalation tool's YES-list («ESCRIBIR a una persona o gestionar CON ella… el widget es solo su espejo»,
added by V2-693 two days earlier), the `widget_data` description («cancelar un COMPROMISO real… la acción va
en su sitio → escalate»), the worker's method («los widgets son solo ESPEJOS locales, NUNCA el objetivo»),
and the auditor's risk signal («¿reflejo local de una acción real no ejecutada?»). The code, meanwhile:
the agenda IS the calendar (V2-643, two-way Google sync) and `send_to` executes an order directly and opens
the engine-owned errand (V2-692). Result: «write to Kryptonite and organise a meeting» went to a shell
worker for six minutes with zero messages, and one `cancel_meeting` was executed twice by two executors.

These cases pin that the four surfaces now say the SAME thing, so the next fix to one of them cannot
silently re-open the contradiction.
"""
from __future__ import annotations

import pathlib
import re

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").lower()


# ── the escalation tool ─────────────────────────────────────────────────────────────────────────────────

# ── widget_data ─────────────────────────────────────────────────────────────────────────────────────────

# ── the worker's method ─────────────────────────────────────────────────────────────────────────────────

def test_the_worker_is_told_the_connected_widget_is_the_source():
    from nucleo.workers import prompts as dp
    text = _norm(dp._METHOD_BLOCK)
    assert "es la fuente" in text and "la agenda es el calendario" in text
    assert "solo espejos" not in text and "nunca el objetivo" not in text


def test_the_worker_operates_a_connected_widget_with_the_cli_never_its_web():
    from nucleo.workers import prompts as dp
    text = _norm(dp._METHOD_BLOCK)
    assert "nunca conduciendo su web" in text


# ── the four surfaces agree, structurally ───────────────────────────────────────────────────────────────

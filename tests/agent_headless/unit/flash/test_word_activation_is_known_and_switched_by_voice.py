"""Word activation: the agent knows what it is, and his voice switches it as the button does, on desktop and phone (V2-929).

The operator, 2026-11-17: «activa eso de la palabra de activación» has to work by voice, not only by the button, on
the phone and on the desktop — and the agent has to know what word activation is if somebody asks. Three facts:

1. KNOWLEDGE — every turn's live state carries the mode under the names people use for it («palabra de activación»,
   «word activation», «wake word»), its word, its state, and which tool switches it — never a literal «zaelar» as the
   word; what it IS FOR and that its button exists on desktop AND phone is self-knowledge, answered by `about_self`
   from its catalogue entry (`wake_word`, V2-932) in every shipped language — not prose paid on every turn;
2. VOICE — the brief's sure verdict switches it both ways, persists it where the button writes, and announces it with
   the same `orb:attention` event the button's change sends;
3. BOTH SHELLS — that event is applied by the one SSE reader both the desktop and the phone shell open.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ENGINE = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("code,shells", [("es", ("ordenador", "móvil")), ("en", ("computer", "phone"))])
def test_what_word_activation_is_and_its_button_on_both_shells_is_in_the_self_catalogue(code, shells):
    from nucleo.self import about
    assert "wake_word" in about.topics(), "about_self cannot answer what word activation is"
    w = about.words(code)["topics"]["wake_word"]
    assert w.get("what") and w.get("voice"), "what it is for and how it is said"
    assert all(s in w.get("button", "") for s in shells), "the button lives on both shells"


def test_the_desktop_and_the_phone_shell_apply_the_same_event():
    sse = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert re.search(r'd\.label === "orb:attention"\)\s*\{[^}]*store\.setAttentionMode', sse), \
        "the shared SSE reader no longer applies a spoken switch"
    desktop = (ENGINE / "frontend/app/main.js").read_text(encoding="utf-8")
    phone = (ENGINE / "frontend/mobile/app/main.js").read_text(encoding="utf-8")
    assert "services/sse.js" in desktop and "services/sse.js" in phone, "a shell stopped reading the shared SSE"

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

import asyncio
import re
from pathlib import Path

import pytest

from nucleo.turn import identity

ENGINE = Path(__file__).resolve().parents[4]


def _lines(monkeypatch, mode: str, name: str) -> str:
    import config.settings as settings
    real = settings.get
    monkeypatch.setattr(settings, "get", lambda k, d=None: mode if k == "attention_mode" else real(k, d))
    from nucleo.flash import style_directive
    return "\n".join(style_directive.prompt_lines({"assistant_name": name}))


@pytest.mark.parametrize("mode,state", [("always", "desactivado"), ("smart", "ACTIVADO")])
def test_the_agent_knows_what_word_activation_is_and_how_it_is_switched(monkeypatch, mode, state):
    line = _lines(monkeypatch, mode, "Johnny")
    for named in ("palabra de activación", "word activation", "WAKE WORD"):
        assert named in line, f"the mode is not known by the name «{named}»"
    assert "«Johnny»" in line and "zaelar" not in line.lower().replace("set_style_directive", "")
    assert "set_style_directive" in line, "the spoken order's door"
    assert state in line


@pytest.mark.parametrize("code,shells", [("es", ("ordenador", "móvil")), ("en", ("computer", "phone"))])
def test_what_word_activation_is_and_its_button_on_both_shells_is_in_the_self_catalogue(code, shells):
    from nucleo.self import about
    assert "wake_word" in about.topics(), "about_self cannot answer what word activation is"
    w = about.words(code)["topics"]["wake_word"]
    assert w.get("what") and w.get("voice"), "what it is for and how it is said"
    assert all(s in w.get("button", "") for s in shells), "the button lives on both shells"


def test_an_unnamed_agent_names_the_catalogue_default_as_its_word(monkeypatch):
    assert "«Johnny»" in _lines(monkeypatch, "always", "")


def _brief(choice, conf=0.95):
    import threading
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {identity.KEY: {"choice": choice, "confidence": conf}}}


@pytest.mark.parametrize("choice,mode", [(identity.NAME_ONLY, "smart"), (identity.ALWAYS, "always")])
def test_his_voice_switches_it_both_ways_where_the_button_writes(monkeypatch, choice, mode):
    wrote, events = {}, []
    from config import settings as cfg
    monkeypatch.setattr(cfg, "update", lambda fields: wrote.update(fields))
    got = asyncio.run(identity.settle(_brief(choice), "", lambda *a, **k: events.append((a, k))))
    assert got == mode and wrote == {"attention_mode": mode}
    assert any(a[:2] == ("ui", "orb:attention") and k["extra"]["state"] == mode for a, k in events), \
        "the shells were not told"


def test_an_unsure_verdict_switches_nothing(monkeypatch):
    wrote = {}
    from config import settings as cfg
    monkeypatch.setattr(cfg, "update", lambda fields: wrote.update(fields))
    assert asyncio.run(identity.settle(_brief(identity.NAME_ONLY, 0.5), "", lambda *a, **k: None)) == ""
    assert wrote == {}


def test_the_desktop_and_the_phone_shell_apply_the_same_event():
    sse = (ENGINE / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    assert re.search(r'd\.label === "orb:attention"\)\s*\{[^}]*store\.setAttentionMode', sse), \
        "the shared SSE reader no longer applies a spoken switch"
    desktop = (ENGINE / "frontend/app/main.js").read_text(encoding="utf-8")
    phone = (ENGINE / "frontend/mobile/app/main.js").read_text(encoding="utf-8")
    assert "services/sse.js" in desktop and "services/sse.js" in phone, "a shell stopped reading the shared SSE"

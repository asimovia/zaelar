"""A failed kickoff never asks the operator to repeat himself (V2-789).

The first turn of a session is the agent's greeting: it answers nothing the operator said. When the model behind it
failed — a provider 503, a stall, a fault of ours — the turn fell to the reply-shaped «say that again?», asking him to
repeat words he never spoke. The fallback line is now chosen by what the turn IS: the kickoff gets the i18n
`kickoff_fallback`, a reply keeps `say_again`. Every variant below crosses failure cause × language × turn shape.

Disarm: make `turn_failure._fallback_line` ignore `first_turn` (always `say_again`) → red.
"""
from __future__ import annotations


import pytest

from i18n import langs


@pytest.fixture
def _no_ladder(monkeypatch):
    """The provider verdict is not under test: an outage with a stand-in still available (not dry)."""
    from nucleo.llm import provider_failure
    monkeypatch.setattr(provider_failure, "handle", lambda *a, **k: {"relay": None, "dry": False})


def test_both_shipped_languages_carry_a_kickoff_fallback():
    for code in ("es", "en"):
        line = langs.spec(code).kickoff_fallback
        assert line and line != langs.spec(code).say_again, (code, line)

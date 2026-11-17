"""Demo pass 45 (2026-09-29), C2→C3: the model asked «I'll write to Rowan on Telegram: … Shall I send it?» for a message
nobody had asked for; the next turn — «ok book it, call it catch up with rowan», an order about the CALENDAR —
matched `ok` in the yes/no table and the Telegram went out. A bare answer still resolves at once; a reply that
carries its own words never sends on a word (V2-878 §4: the second model that used to be asked here is gone)."""
from tests import voice_turn_source as _vts
import pytest

from widgets import confirm

_Q = "I'll write to Rowan on Telegram: «you free for a 45-minute call tomorrow?». Shall I send it?"


@pytest.fixture(autouse=True)
def pending():
    confirm.reset()
    confirm.request("data", "mensajeria", _Q, op={"action": "send_to", "payload": {}}, notify_ui=False)
    yield
    confirm.reset()


@pytest.fixture
def no_model(monkeypatch):
    """V2-878 §4: the confirmation judge is gone — no model is ever asked here, on any reply."""
    from nucleo.llm import fast_client

    async def _never(*a, **k):
        raise AssertionError("a model was asked whether a reply answers the pending question")
    monkeypatch.setattr(fast_client.FastClient, "complete", _never)


def test_a_different_order_that_starts_with_ok_confirms_nothing(no_model):
    assert confirm.answers_pending("ok book it, call it catch up with rowan") is None


def test_a_declared_answer_resolves_at_once(no_model, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert confirm.answers_pending("Yes") == "yes"
    assert confirm.answers_pending("no.") == "no"
    assert confirm.answers_pending("ok go ahead") is None, "V2-878 §4b: a longer reply never sends on its word"


def test_both_voice_sites_and_the_gate_use_it():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert _vts.read(root / "voice/engine/llm/providers/nucleo.py").count("_wconfirm.answers_pending(text, _brief)") == 2
    assert "_c.answers_pending(text" in (root / "nucleo/turn/confirm_gates.py").read_text("utf-8")

"""Demo pass 45 (2026-09-29), C2→C3: the model asked «I'll write to Rowan on Telegram: … Shall I send it?» for a message
nobody had asked for; the next turn — «ok book it, call it catch up with rowan», an order about the CALENDAR —
matched `ok` in the yes/no table and the Telegram went out. A bare answer still resolves at once; a reply that
carries its own words never sends on a word — the brief's pick over the question's row reads it (V2-878 §4: the
second model that used to be asked here is gone)."""
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


def _bound(choice: str):
    import threading
    from nucleo.cli import worker_api_bind as bind
    ev = threading.Event()
    ev.set()
    return {"event": ev, "_call_id": "t", "turn_id": "t", "open_ids": [],
            "result": {"_call_id": "t", bind.KEY: {"choice": choice, "confidence": 0.95, "probs": {choice: 0.95}}}}


def test_a_different_order_that_starts_with_ok_confirms_nothing(no_model):
    assert confirm.answers_pending("ok book it, call it catch up with rowan") is None


def test_a_bare_answer_resolves_at_once(no_model):
    assert confirm.answers_pending("yes") == "yes"
    assert confirm.answers_pending("ok go ahead") == "yes"
    assert confirm.answers_pending("no, cancel it") == "no"


def test_a_long_yes_is_the_briefs_pick_never_a_second_model(no_model):
    """The question waits on its row; the brief's binding read it — its pick answers the row, not the words here."""
    (p,) = confirm.pending().values()
    assert p.get("ask_id"), "the question is not on a row"
    said = "yeah sure, send that to him right now please"
    assert confirm.answers_pending(said, _bound(f"{p['ask_id']}#0")) is None
    assert confirm.answers_pending(said) is None, "a longer reply never sends on its word"


def test_both_voice_sites_and_the_gate_use_it():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert _vts.read(root / "voice/engine/llm/providers/nucleo.py").count("_wconfirm.answers_pending(text, _brief)") == 2
    assert "_c.answers_pending(text" in (root / "nucleo/turn/confirm_gates.py").read_text("utf-8")

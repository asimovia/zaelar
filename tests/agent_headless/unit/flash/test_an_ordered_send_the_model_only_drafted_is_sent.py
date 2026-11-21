"""An ORDERED act that leaves runs when the model only prepared it (2026-10-15, the operator's 70%).

Live bench E3: «send the invoice to quinn, tell him we're already trying inworld and he should book it» — order at
1.00, `mensajeria:forward` at 0.79, and the model called `draft`: 2 of 7 runs sent nothing and said «Done.». The
mirror of the voice rule that runs the verdict over a model call that LEAVES when nobody asked for it.

Since V2-852 M2 the act that leaves is the turn's one TASK, never run inline: the verdict's forward is what the
turn routes (and no «the turn already acted» guard may annul it — the dry case below lost the send exactly so).

Disarm: return None from `ordered_send.instead` → red; unwire it from `verdict_card.retarget` → the wiring test red.
"""
from __future__ import annotations

import threading

import pytest

from tests import widget_data_rig as rig

from nucleo.acts import message_repair as ordered_send

SAID = "send the invoice to quinn, tell him we're already trying inworld and he should book it"


def _brief(target: str, conf: float, kind: str = "order") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {"screen_action": {"choice": target, "confidence": conf},
                       "request_type": {"choice": kind, "confidence": 1.0}}}


@pytest.fixture(autouse=True)
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    import server.voice_api as _va
    monkeypatch.setattr(_va, "open_instances", lambda: ["mensajeria"])


def test_a_draft_under_a_sure_ordered_forward_becomes_the_forward():
    got = ordered_send.ordered_instead(_brief("mensajeria:forward", 0.79), "mensajeria", "draft",
                               {"text": "We're already trying Inworld — please book it."}, SAID)
    assert got and got[0] == "forward", got
    assert got[1].get("text", "").startswith("We're already trying Inworld") and got[1].get("contact"), got


def test_under_the_bar_or_a_model_that_sends_or_a_question_nothing_changes():
    draft = {"text": "book it"}
    assert ordered_send.ordered_instead(_brief("mensajeria:forward", 0.55), "mensajeria", "draft", draft, SAID) is None
    assert ordered_send.ordered_instead(_brief("mensajeria:forward", 0.9), "mensajeria", "send_to", draft, SAID) is None
    assert ordered_send.ordered_instead(_brief("mensajeria:forward", 0.9, kind="question"), "mensajeria", "draft", draft, SAID) is None
    assert ordered_send.ordered_instead(_brief("mensajeria:forward", 0.9), "mensajeria", "forward", draft, SAID) is None


@pytest.fixture()
def gate_scene(tmp_path, monkeypatch):
    from nucleo import his_words, untrusted
    rig.scene(tmp_path, monkeypatch)
    yield
    untrusted.reset()
    his_words.reset()

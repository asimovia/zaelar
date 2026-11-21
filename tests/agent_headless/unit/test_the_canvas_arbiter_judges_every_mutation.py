"""The canvas arbiter judges every mutation by WHO ordered it (V2-653; INI-078 L1, option (b): provenance only).

The provenance set is closed: the operator's hands, the canvas reporting what it did, the lifecycle, a task's own card
(one sheet per task), the manager's turn (`turn:<effect>`), a seeded phrase. An unknown provenance is REFUSED
(`unknown-src`) — never judged by reading his words, which is what the old turn's word licences did. The shadow tap
writes the same verdict, unenforced, for a canvas act that did not cross the door.

Disarm: make the last line of `_decide` allow — the unknown-provenance case goes red.
"""
import re
from pathlib import Path

import pytest

from tests import voice_turn_source as _vts
from nucleo.acts import canvas_arbiter as arb
from nucleo.acts import canvas_turn as turn

ENGINE = Path(__file__).resolve().parents[3]


def test_the_operators_hands_are_always_licensed():
    assert arb.decide("show", "agenda", "user").allow is True
    assert arb.decide("close", "youtube", "user").allow is True


def test_lifecycle_and_system_writes_pass():
    assert arb.decide("show", "agenda", "system").rule == "lifecycle"
    assert arb.decide("close", "", "system:reset").rule == "lifecycle"


def test_a_worker_mutation_rides_its_task():
    v = arb.decide("data", "results", "worker:t3", action="present")
    assert v.allow is True and v.rule == "task-owned" and v.evidence.get("tid") == "t3"


def test_the_managers_act_signs_with_its_reservation():
    v = arb.decide("show", "imagenes", "turn:e_42")
    assert v.allow is True and v.rule == "turn-owned" and v.evidence.get("effect") == "e_42"


def test_the_action_maps_seeded_phrase_is_the_license():
    assert arb.decide("close", "mensajeria", "actionmap").rule == "seeded-grammar"


@pytest.mark.parametrize("src", ["flash", "backstop", "quien-sabe", ""])
def test_an_unknown_provenance_is_refused_never_judged_by_words(src):
    """The old turn's `flash`/`backstop` included: they are no provenance any live door signs with."""
    v = arb.decide("show", "agenda", src)
    assert v.allow is False and v.rule == "unknown-src"


def test_the_tree_never_raises_on_garbage_and_an_unknown_op_inherits_nobodys_pass():
    v = arb.decide(None, None, None, action=None)  # type: ignore
    assert v.allow is False and v.rule == "unknown-op"
    assert arb.decide("teleport", "agenda", "system").rule == "unknown-op"


# ── the shadow tap ───────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def verdicts(monkeypatch):
    """Capture the arbiter's own emits without touching the real observer (no file writes in a unit)."""
    import voice.observer as obs
    out = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        out.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    return out


def test_the_tap_judges_a_widget_command_by_its_provenance(verdicts):
    turn.shadow_tap("widget", "close", "", "", {"id": "youtube", "src": "turn:e_1"})
    turn.shadow_tap("widget", "show", "", "", {"id": "agenda", "src": "flash"})
    assert [(v["rule"], v["allow"], v["shadow"]) for v in verdicts] == [
        ("turn-owned", True, True), ("unknown-src", False, True)]


def test_a_ui_click_travels_as_an_action_event_and_is_judged(verdicts):
    turn.shadow_tap("widget", "action", "", "", {"id": "agenda", "action": "show_day", "src": "user"})
    assert verdicts and verdicts[0]["rule"] == "operator-hands" and verdicts[0]["allow"] is True


def test_the_tap_never_raises_even_on_garbage(verdicts):
    turn.shadow_tap("widget", "show", None, None, "not-a-dict")  # type: ignore
    turn.shadow_tap("widget", "data:", None, None, {})  # type: ignore


def _stripped(path: str) -> str:
    return re.sub(r"(?m)#.*$", "", _vts.read(ENGINE / path))


def test_the_observer_calls_the_tap_and_classifies_the_kind():
    assert "_arb.shadow_tap(kind, label, text, role, extra)" in _stripped("voice/observer.py")
    import voice.observer as obs
    assert obs._CAT.get("arbiter") == "widget", "the verdict kind must belong to a viewer family"

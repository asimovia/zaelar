"""An unmet end state runs the app's declared next step before it is said unmet (operator, 2026-11-08).

«Si falla el primer intento, tiene que iterar hasta que el arnés se cumpla.» Measured: a request for an artist was
refused three times on the same provider and nothing tried another; the inline circuit only settled `unmet`.

Mechanism (`nucleo/circuit/__init__.py::_next_step`): an action may declare `on_unmet: [{action, payload}]` in its
manifest — `{key}` filled from the original payload. When its end state is still unmet past the grace period the
circuit runs the next step through the widget's own funnel (`server_api.brain_action`), keeps the SAME end state
owed with a fresh grace, at most `MAX_STEPS`; an action that declares nothing is settled as before. Nothing is
guessed: the steps are the app's data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo import circuit
from nucleo.circuit import spec as _spec


@pytest.fixture
def world(monkeypatch):
    ran: list = []

    async def brain_action(wid, action, payload):
        ran.append((wid, action, payload))
        return {"ok": True}
    monkeypatch.setattr("widgets.server_api.brain_action", brain_action)
    manifests = {"musica": {"actions": {
        "play": {"done_when": {"widget": "musica", "field": "here.title", "expect": "changed"},
                 "on_unmet": [{"action": "play", "payload": {"query": "{query}", "source": "youtube"}}]},
        "pause": {"done_when": {"widget": "musica", "field": "here.title", "expect": "absent"}}}}}
    monkeypatch.setattr("widgets.runtime.get", lambda wid: manifests.get(wid))
    return ran


def _entry(action, payload):
    return {"widget": "musica", "action": action, "payload": payload, "born": 1.0, "tries": 0, "id": "s1",
            "done_when": {"widget": "musica", "field": "here.title", "expect": "changed"}}


def test_the_declared_step_runs_with_the_original_words(world):
    e = _entry("play", {"query": "lena hall"})
    assert circuit._next_step(e, now=100.0) is True
    assert world == [("musica", "play", {"query": "lena hall", "source": "youtube"})]
    assert e["step"] == 1 and e["born"] == 100.0 and e["tries"] == 1, "the same end state stays owed, fresh grace"


def test_the_steps_are_bounded_then_it_is_said_unmet(world):
    e = _entry("play", {"query": "lena hall"})
    assert circuit._next_step(e, now=1.0) is True
    assert circuit._next_step(e, now=2.0) is False, "one declared step: the second unmet is the verdict"
    assert len(world) == 1


def test_an_action_that_declares_nothing_is_settled_as_before(world):
    assert circuit._next_step(_entry("pause", {}), now=1.0) is False and world == []


def test_the_tick_runs_the_step_instead_of_settling(world, monkeypatch):
    e = _entry("play", {"query": "lena hall"})
    monkeypatch.setattr(_spec, "open_specs", lambda now=None: [e])
    monkeypatch.setattr(_spec, "attest", lambda entry, now=None: False)
    settled: list = []
    monkeypatch.setattr(circuit, "_settle_unmet_inline", lambda entry, now: settled.append(entry))
    circuit.tick(now=1.0 + circuit.INLINE_GRACE_S + 10)
    assert world and not settled, "past the grace, the declared step ran instead of the unmet verdict"


def test_an_opened_end_state_keeps_the_payload_its_steps_are_rendered_from(monkeypatch):
    monkeypatch.setattr(_spec, "render", lambda wid, action, payload: {"widget": wid, "field": "x", "expect": "present"})
    e = _spec.open_for_action("musica", "play", {"query": "creep"})
    assert e is not None and e["payload"] == {"query": "creep"}


def test_every_declared_step_names_an_action_its_app_has():
    for mf in sorted(Path("widgets").glob("*/manifest.json")):
        acts = (json.loads(mf.read_text(encoding="utf-8")).get("actions") or {})
        for name, spec in acts.items():
            for step in (spec or {}).get("on_unmet") or [] if isinstance(spec, dict) else []:
                assert step.get("action") in acts, f"{mf.parent.name}:{name} steps to an unknown action {step}"

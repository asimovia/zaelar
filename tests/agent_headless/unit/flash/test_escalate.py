"""Tests for nucleo/acts/errand.py (V2-004 · T64) — escalation stub: registration + bus event."""
import pytest

import bus
from nucleo.acts import errand as escalate


@pytest.fixture(autouse=True)
def _reset():
    escalate.reset()
    yield
    escalate.reset()


def test_escalate_registers_and_emits_bus():
    seen = []
    sink = lambda rec: seen.append(rec) if rec["topic"] == "escalate.requested" else None
    bus.add_sink(sink)
    try:
        tid = escalate.escalate_to_slowbrain("recuerda que mi coche está en el taller", context={"src": "voice"})
    finally:
        bus.remove_sink(sink)
    assert isinstance(tid, int) and tid > 0
    assert len(seen) == 1
    assert seen[0]["payload"]["id"] == tid
    assert "coche" in seen[0]["payload"]["request"]
    # V2-844 F1a: the errand is born at the portal — its row's uid travels with it for the dispatcher to adopt
    assert seen[0]["payload"]["context"] == {"src": "voice", "born_uid": seen[0]["payload"]["context"]["born_uid"]}
    assert seen[0]["payload"]["context"]["born_uid"].endswith(f"-{tid}")


def test_registry_bounded():
    for i in range(30):
        escalate.escalate_to_slowbrain(f"tarea {i}")
    assert len(escalate.pending()) <= 12

"""Transport is billed on the time the voice room was really up, booked to the session that ran it.

A work session outlives its voice (the room closes, the session waits for the idle timeout), and a host frozen with a
session open comes back to a session whose clock kept running through the freeze. Billing the session's wall-clock
charged both. And the charge used to read the session id AFTER the session closed, so it opened a NEW session and was
booked there."""
from __future__ import annotations


import pytest

from nucleo.energy import meter, meter_report
from observability import identity


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(identity, "_report_to_control_plane", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_emit_session", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_start_heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(identity, "_agent_stopped", lambda: False)
    monkeypatch.setattr(identity, "_voice_event", lambda *a, **k: None)
    identity._voice.update(ms=0, open={}, seq=0)
    identity.end_session("test")
    identity._voice.update(ms=0, open={}, seq=0)
    yield
    identity._voice.update(ms=0, open={}, seq=0)


class _Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> int:
        return round(self.t * 1000)


def _billed(monkeypatch) -> list[tuple[float, str | None]]:
    out: list = []
    monkeypatch.setattr(meter_report, "report_transport_usage",
                        lambda *, participant_seconds, session_id=None, **k: out.append((participant_seconds, session_id)))
    monkeypatch.setattr(meter, "report_transport_usage", meter_report.report_transport_usage)
    return out


def test_a_session_open_hours_after_its_voice_closed_bills_only_the_voice(monkeypatch):
    clock = _Clock(1_000_000.0)
    monkeypatch.setattr(identity, "_now_ms", clock)
    billed = _billed(monkeypatch)
    sid = identity.begin_session(source="frontend")["id"]
    tok = identity.voice_connected()
    clock.t += 180                       # three minutes of voice
    identity.voice_disconnected(tok)
    clock.t += 3 * 3600                  # the session stays open for hours with no voice
    identity.end_session("idle_timeout")
    assert [(round(x, 3), y) for x, y in billed] == [(360.0, sid)], \
        "transport = 3 min of voice × 2 participants, booked to the session that ran it"


def test_a_freeze_with_the_voice_open_is_not_billed(monkeypatch):
    clock = _Clock(2_000_000.0)
    monkeypatch.setattr(identity, "_now_ms", clock)
    billed = _billed(monkeypatch)
    sid = identity.begin_session(source="frontend")["id"]
    identity.voice_connected()
    clock.t += 60
    clock.t += 10_000                    # the host was frozen
    identity.note_suspended(10_000_000)
    clock.t += 30
    identity.end_session("idle_timeout")
    assert [(round(x, 3), y) for x, y in billed] == [(180.0, sid)]


def test_a_session_with_no_voice_bills_no_transport(monkeypatch):
    billed = _billed(monkeypatch)
    identity.begin_session(source="frontend")
    identity.end_session("frontend")
    assert billed == []


def test_the_charge_names_its_session_instead_of_opening_one(monkeypatch):
    """The ledger POST runs after the session closed: reading `session_id()` there opened a new one."""
    sent: list = []

    async def _post(energy, kind, meta=None):
        sent.append(meta)
    monkeypatch.setattr(meter, "enabled", lambda: True)
    monkeypatch.setattr(meter, "transport_cost_to_energy", lambda **k: 5.0)
    monkeypatch.setattr(meter, "_fire_and_forget", lambda e, kind, meta=None: sent.append(meta))
    meter_report.report_transport_usage(participant_seconds=10.0, session_id="s-ran")
    assert sent and sent[0]["session_id"] == "s-ran"

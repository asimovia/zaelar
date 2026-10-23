"""The Energy gauge learns the balance from the LEASE answer, and goes down with the lease's local spend.

The gauge used to learn the balance only from usage-report responses. Under the lease a Machine does not report each
charge, so it never learned it: an account with 397 Energy showed an unlit gauge. The lease answer carries the
balance and, when the cloud sends them, the plan's gauge facts (`cycle_energy`, `scale`, `tier`), which make the
gauge «the cycle's Energy minus what was spent».
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import energy_lease, energy_meter


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    energy_lease._reset_for_tests()
    energy_meter._reset_for_tests()
    monkeypatch.setattr(energy_lease, "_persist", lambda: None)
    monkeypatch.setattr(energy_lease, "enabled", lambda: True)
    monkeypatch.setattr(energy_meter, "enabled", lambda: True)
    monkeypatch.setattr(energy_meter, "_load_once", lambda: None)
    yield
    energy_lease._reset_for_tests()
    energy_meter._reset_for_tests()


def _lease_answer(monkeypatch, body):
    import httpx

    class _R:
        status_code = 200

        def json(self):
            return body

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _C)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.example.test")


def test_a_lease_answer_tells_the_gauge_the_balance_and_the_cycle(monkeypatch):
    _lease_answer(monkeypatch, {"ok": True, "lease_id": "L1", "energy": 40, "ttl_s": 1800, "balance": 397,
                                "plan": {"key": "free", "name": "Free", "cycle_energy": 500, "scale": 13000, "tier": 0}})
    assert asyncio.run(energy_lease.ensure(reason="boot", force=True))
    snap = energy_meter.snapshot()
    assert snap["known"] and snap["balance"] == 397 and snap["capacity"] == 500
    assert snap["plan"] == {"key": "free", "name": "Free", "tier": 0, "scale": 13000}


def test_the_gauge_goes_down_with_the_local_spend(monkeypatch):
    _lease_answer(monkeypatch, {"ok": True, "lease_id": "L1", "energy": 40, "ttl_s": 1800, "balance": 397,
                                "plan": {"name": "Free", "cycle_energy": 500}})
    asyncio.run(energy_lease.ensure(reason="boot", force=True))
    energy_lease.note_spend(7)
    assert energy_meter.snapshot()["balance"] == pytest.approx(390)


def test_a_refused_lease_still_tells_the_balance(monkeypatch):
    _lease_answer(monkeypatch, {"ok": False, "error": "plan_expired", "balance": 0, "plan": {"name": "Free"}})
    assert not asyncio.run(energy_lease.ensure(reason="boot", force=True))
    snap = energy_meter.snapshot()
    assert snap["known"] and snap["balance"] == 0


def test_without_gauge_facts_the_capacity_is_the_highest_balance_seen():
    energy_lease._gauge_from_lease({"balance": 800})
    energy_lease._gauge_from_lease({"balance": 600})
    assert energy_meter.snapshot()["capacity"] == 800

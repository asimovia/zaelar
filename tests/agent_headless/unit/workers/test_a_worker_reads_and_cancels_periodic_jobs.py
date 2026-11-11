"""V2-883 — a worker holding an order over a periodic job has the job's reader and door.

Measured shape: the worker asked `read_widget` for the job four times — refused each time with nothing to offer, a
periodic job not being a card — then read another card's manifest and wrote status reports for minutes. The jobs
have ONE reader (`scheduler.ref_index`) and ONE door by reference (`scheduler.unschedule`); the worker reaches both
through the bridge (`act schedules`, `act unschedule`), and «no such card» names them.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.cli import worker_api_exec as X
from nucleo.cli import worker_policy as P
from nucleo.pulse import scheduler


@pytest.fixture
def two_jobs():
    a = scheduler.create("mira el pedido", "0 11 * * *", name="Package tracking for order 77-1")
    b = scheduler.create("water", "every 2d", name="Water the balcony plants")
    yield str(a["id"]), str(b["id"])
    for j in scheduler.list_jobs(active_only=True):
        scheduler.cancel(str(j["id"]))


def test_both_doors_are_known_and_allowed():
    for act in ("schedules", "unschedule"):
        assert act in P._KNOWN_ACTS and P.classify_act(act, {}) == P.ALLOW, act


def test_the_worker_reads_the_jobs_as_references(two_jobs):
    res = asyncio.run(X._exec_allow("schedules", {}, None))
    ids = {r["id"] for r in res["result"]["jobs"]}
    assert res["ok"] and ids == set(two_jobs), res
    assert all({"id", "label", "field", "hint"} <= set(r) for r in res["result"]["jobs"])


def test_the_worker_cancels_one_by_its_id_and_a_miss_is_not_ok(two_jobs):
    parcel, water = two_jobs
    res = asyncio.run(X._exec_allow("unschedule", {"job": parcel}, None))
    assert res["ok"] and res["result"]["cancelled"] == parcel, res
    assert {str(j["id"]) for j in scheduler.list_jobs(active_only=True)} == {water}
    miss = asyncio.run(X._exec_allow("unschedule", {"job": "the newsletter digest"}, None))
    assert not miss["ok"] and "Water the balcony plants" in miss["candidates"], miss


def test_no_such_card_names_the_jobs_reader():
    res = asyncio.run(X._exec_allow("read_widget", {"id": "tarea-periodica-del-paquete"}, None))
    assert not res["ok"] and "act schedules" in res["error"], res

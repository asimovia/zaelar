"""The one admission exemption: the network's signed wake push reaches `POST /api/a2a/wake` from a peer off this
machine and without a session — and nothing else under /api/a2a/ does. The signature check is the gate."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import a2a.server_api as sapi
from a2a.identity import Identity
from a2a.server_api import WakeGate, wake_exempt

OUTSIDE = ("203.0.113.7", 40000)
BODY = json.dumps({"kind": "mail"})


class FakeAgent:
    def __init__(self):
        self.rows = []

    def emit(self, op, **kw):
        self.rows.append((op, kw))

    def status(self):
        return {"relationships": []}


class FakeJobs:
    def __init__(self):
        self.agent, self.pulls = FakeAgent(), 0

    def wake(self):
        self.pulls += 1
        return 1


class Clock:
    t = 1_800_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def engine(monkeypatch):
    """The real api_guard + ingress middlewares around the real a2a router, A2A switched on over fakes."""
    from server import a2a_api, api_guard, ingress
    key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
    saved = dict(a2a_api._state)
    a2a_api._state.update(agent=jobs.agent, jobs=jobs, gate=WakeGate(key.pub_b64, clock=clock), cards=None)
    monkeypatch.setattr(a2a_api, "enabled", lambda: True)
    app = FastAPI()
    app.include_router(a2a_api.router)
    ingress.install(app)
    api_guard.install(app)
    yield app, key, jobs, clock
    a2a_api._state.clear()
    a2a_api._state.update(saved)


def _cloud(monkeypatch):
    from nucleo.energy import routing
    monkeypatch.setattr(routing, "is_account_routing_machine", lambda: True)
    monkeypatch.setattr(routing, "my_machine_id", lambda: "m1")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.invalid")


def _signed(key, clock, body=BODY, path="/api/a2a/wake"):
    return {"MeshKore-Sig": key.mk_sig("POST", path, body, ts=int(clock())), "Content-Type": "application/json"}


@pytest.mark.parametrize("cloud", [False, True])
def test_a_signed_wake_from_outside_is_admitted_and_pulls_once(engine, monkeypatch, cloud):
    app, key, jobs, clock = engine
    if cloud:
        _cloud(monkeypatch)
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    r = c.post("/api/a2a/wake", content=BODY, headers=_signed(key, clock))
    assert r.status_code == 202 and jobs.pulls == 1


@pytest.mark.parametrize("cloud", [False, True])
def test_unsigned_forged_and_replayed_wakes_are_refused_without_a_pull(engine, monkeypatch, cloud):
    app, key, jobs, clock = engine
    if cloud:
        _cloud(monkeypatch)
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    assert c.post("/api/a2a/wake", content=BODY).status_code == 401
    forged = _signed(Identity.generate(), clock)
    assert c.post("/api/a2a/wake", content=BODY, headers=forged).status_code == 401
    good = _signed(key, clock)
    assert c.post("/api/a2a/wake", content=BODY, headers=good).status_code == 202
    clock.t += 10                                             # past the coalescing window: a replay must still fail
    assert c.post("/api/a2a/wake", content=BODY, headers=good).status_code == 401
    other = json.dumps({"kind": "mail", "x": 1})              # signed for another body
    assert c.post("/api/a2a/wake", content=other, headers=_signed(key, clock)).status_code == 401
    assert jobs.pulls == 1


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/a2a/status"), ("GET", "/api/a2a/network"), ("POST", "/api/a2a/cards/x"),
    ("GET", "/api/a2a/wake"), ("POST", "/api/a2a/wakeX"), ("POST", "/api/a2a/wake/"),
    ("POST", "/api/a2a/wake/x"), ("POST", "/api/a2a/wake%2F..%2Fcards"),
])
def test_every_other_a2a_route_and_variant_stays_refused_from_outside(engine, monkeypatch, cloud, method, path):
    app, key, jobs, clock = engine
    if cloud:
        _cloud(monkeypatch)
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    r = c.request(method, path, content=BODY, headers=_signed(key, clock, path=path))
    assert r.status_code in (401, 403) and jobs.pulls == 0


def test_dot_segments_and_shape_never_make_a_path_exempt():
    for p in ("/api/a2a/wake/../cards", "/api/a2a/wake/..", "/api/a2a//wake", "/api/a2a/wakeX", "/api/a2a/wake/",
              "/API/a2a/wake", "/api/a2a/wake?x"):
        assert not wake_exempt(p, "POST", "16", True)
    assert wake_exempt("/api/a2a/wake", "POST", "16", True)
    assert not wake_exempt("/api/a2a/wake", "GET", "16", True)
    assert not wake_exempt("/api/a2a/wake", "POST", "16", False)          # A2A off
    assert not wake_exempt("/api/a2a/wake", "POST", "257", True)          # too big to be a wake
    assert not wake_exempt("/api/a2a/wake", "POST", None, True)           # chunked / undeclared
    assert not wake_exempt("/api/a2a/wake", "POST", "-1", True)


def test_a_large_body_is_not_exempt_from_outside(engine):
    app, key, jobs, clock = engine
    big = json.dumps({"kind": "mail", "pad": "x" * 400})
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    assert c.post("/api/a2a/wake", content=big, headers=_signed(key, clock, body=big)).status_code == 403
    assert jobs.pulls == 0


def test_a2a_off_is_404_and_not_exempt(engine, monkeypatch):
    from server import a2a_api
    app, key, jobs, clock = engine
    a2a_api._state.update(jobs=None, gate=None, agent=None)
    assert TestClient(app).post("/api/a2a/wake", content=BODY).status_code == 404
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    assert c.post("/api/a2a/wake", content=BODY, headers=_signed(key, clock)).status_code == 403


def test_no_pinned_key_is_503_without_any_work(engine):
    from server import a2a_api
    app, key, jobs, clock = engine
    a2a_api._state["gate"] = WakeGate(None)
    c = TestClient(app, client=OUTSIDE, base_url="http://engine.example")
    assert c.post("/api/a2a/wake", content=BODY, headers=_signed(key, clock)).status_code == 503
    assert jobs.pulls == 0 and jobs.agent.rows == []


def test_rate_limit_per_source_and_verified_wakes_coalesce():
    key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
    gate = WakeGate(key.pub_b64, clock=clock)
    codes = [gate.handle(jobs, {}, BODY, source="1.2.3.4")[0] for _ in range(sapi.WAKE_PER_SOURCE + 2)]
    assert codes[:sapi.WAKE_PER_SOURCE] == [401] * sapi.WAKE_PER_SOURCE and codes[-2:] == [429, 429]
    assert gate.handle(jobs, _signed(key, clock), BODY, source="5.6.7.8")[0] == 202       # another source
    assert gate.handle(jobs, _signed(key, clock), BODY, source="5.6.7.8") == (202, {"coalesced": True})
    assert jobs.pulls == 1
    clock.t += sapi.WAKE_WINDOW_S + 1
    assert gate.handle(jobs, _signed(key, clock), BODY, source="1.2.3.4")[0] == 202       # window passed
    assert jobs.pulls == 2


def test_disarm_without_the_signature_check_a_forged_wake_would_pull(monkeypatch):
    """Proves the refusal tests above bite on the signature check, not on something incidental."""
    def forged_pulls() -> int:
        jobs, clock = FakeJobs(), Clock()
        gate = WakeGate(Identity.generate().pub_b64, clock=clock)
        gate.handle(jobs, _signed(Identity.generate(), clock), BODY, source="x")
        return jobs.pulls
    assert forged_pulls() == 0
    monkeypatch.setattr(sapi, "verify_mk_sig", lambda *a, **k: "")
    assert forged_pulls() == 1

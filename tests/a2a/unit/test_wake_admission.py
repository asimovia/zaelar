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
    from server import a2a_api, api_guard, ingress, operator_gate
    key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
    saved = dict(a2a_api._state)
    a2a_api._state.update(agent=jobs.agent, jobs=jobs, gate=WakeGate(key.pub_b64, clock=clock), cards=None)
    monkeypatch.setattr(a2a_api, "enabled", lambda: True)
    app = FastAPI()
    app.include_router(a2a_api.router)
    ingress.install(app)
    operator_gate.install(app)                              # the same three gates, in the app's own order
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


def test_failed_attempts_are_budgeted_and_never_lock_a_verified_wake_out():
    """Behind a proxy every caller has the same peer address: junk from it must not refuse the network's wake."""
    key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
    gate = WakeGate(key.pub_b64, clock=clock)
    codes = [gate.handle(jobs, {}, BODY, source="1.2.3.4")[0] for _ in range(sapi.WAKE_PER_SOURCE + 2)]
    assert codes[:sapi.WAKE_PER_SOURCE] == [401] * sapi.WAKE_PER_SOURCE and codes[-2:] == [429, 429]
    assert len(jobs.agent.rows) == sapi.WAKE_PER_SOURCE                   # over the budget: no event either
    for i in range(sapi.WAKE_GLOBAL * 2):                                 # and the global budget, from many sources
        gate.handle(jobs, {}, BODY, source=f"10.0.{i}.1")
    assert sum(1 for op, kw in jobs.agent.rows if not kw.get("sig_ok")) == sapi.WAKE_GLOBAL
    assert gate.handle(jobs, _signed(key, clock), BODY, source="1.2.3.4")[0] == 202       # same source, both budgets spent
    assert gate.handle(jobs, _signed(key, clock), BODY, source="1.2.3.4") == (202, {"coalesced": True})
    assert jobs.pulls == 1
    clock.t += sapi.WAKE_COALESCE_S + 1
    assert gate.handle(jobs, _signed(key, clock), BODY, source="1.2.3.4")[0] == 202
    assert jobs.pulls == 2


def _junk(key, clock, nonce):
    """A header that names the pinned key and a fresh ts but carries no valid signature: anyone can send it."""
    return {"MeshKore-Sig": f"v1 {key.pub_b64} {int(clock())} {nonce} AAAA"}


def test_a_flood_of_unsigned_requests_never_reopens_a_replay():
    key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
    gate = WakeGate(key.pub_b64, clock=clock)
    good = _signed(key, clock)
    assert gate.handle(jobs, good, BODY, source="net")[0] == 202
    for i in range(6000):                                                 # past the old 5000-entry clear
        gate.handle(jobs, _junk(key, clock, f"n{i}"), BODY, source=f"s{i}")
    assert len(gate._nonces) == 1                                         # junk nonces are never stored
    clock.t += sapi.WAKE_COALESCE_S + 1
    assert gate.handle(jobs, good, BODY, source="net")[0] in (401, 429) and jobs.pulls == 1
    later = _signed(key, clock)                                           # nor can junk burn a nonce ahead of its owner
    gate.handle(jobs, _junk(key, clock, later["MeshKore-Sig"].split()[3]), BODY, source="x")
    assert gate.handle(jobs, later, BODY, source="net")[0] == 202 and jobs.pulls == 2


def test_the_nonce_window_forgets_only_what_can_no_longer_verify_and_refuses_when_full():
    from a2a.identity import SIG_SKEW_S, BadSignature, NonceWindow
    clock = Clock()
    w = NonceWindow(clock=clock, cap=3)
    for i in range(3):
        w.remember(f"n{i}", int(clock()))
    with pytest.raises(BadSignature):
        w.remember("n3", int(clock()))                                    # full: refused, never cleared
    assert "n0" in w and len(w) == 3
    clock.t += SIG_SKEW_S + 1                                             # those signatures are stale now anyway
    w.remember("n4", int(clock()))
    assert len(w) == 1 and "n0" not in w
    key, jobs = Identity.generate(), FakeJobs()
    gate = WakeGate(key.pub_b64, clock=clock)
    for i in range(50):                                                   # verified wakes over hours stay bounded
        assert gate.handle(jobs, _signed(key, clock), BODY, source="net")[0] == 202
        clock.t += SIG_SKEW_S
    assert len(gate._nonces) <= 2


def test_disarm_recording_the_nonce_before_the_signature_lets_junk_burn_it(monkeypatch):
    """Proves the flood test bites on the order (verify, then record): with the old order junk fills the store and
    burns the nonce of a wake that has not arrived yet."""
    import a2a.identity as ident

    def junk_then_real() -> tuple[int, int]:
        key, jobs, clock = Identity.generate(), FakeJobs(), Clock()
        gate = WakeGate(key.pub_b64, clock=clock)
        real = _signed(key, clock)
        gate.handle(jobs, _junk(key, clock, real["MeshKore-Sig"].split()[3]), BODY, source="x")
        return len(gate._nonces), gate.handle(jobs, real, BODY, source="net")[0]
    assert junk_then_real() == (0, 202)

    def record_first(header, method, path, body, expected_pub_b64=None, now=None, seen_nonces=None):
        nonce = (header or "").split()[3]
        if nonce in seen_nonces:
            raise ident.BadSignature("replayed nonce")
        seen_nonces.remember(nonce, now)
        return ident.verify_mk_sig(header, method, path, body, expected_pub_b64=expected_pub_b64, now=now)
    monkeypatch.setattr(sapi, "verify_mk_sig", record_first)
    assert junk_then_real() == (1, 401)


def test_the_key_is_pinned_only_over_tls_and_only_if_it_is_a_key():
    from types import SimpleNamespace as NS
    from server import a2a_api

    def agent(base, answer):
        def server_key():
            if isinstance(answer, Exception):
                raise answer
            return answer
        return NS(mailbox=NS(http=NS(base=base), server_key=server_key))
    pub = Identity.generate().pub_b64
    assert a2a_api._pin(agent("https://net.example", {"pubkey": pub})) == pub
    assert a2a_api._pin(agent("http://127.0.0.1:8787", {"pubkey": pub})) == pub      # the lab, on this machine
    assert a2a_api._pin(agent("http://net.example", {"pubkey": pub})) is None        # plain http: never pinned
    assert a2a_api._pin(agent("https://net.example", {"pubkey": "short"})) is None
    assert a2a_api._pin(agent("https://net.example", {"pubkey": None})) is None
    assert a2a_api._pin(agent("https://net.example", {})) is None
    assert a2a_api._pin(agent("https://net.example", RuntimeError("down"))) is None


def test_two_pulls_never_run_at_once(tmp_path):
    import threading
    import a2a
    agent = a2a.A2AAgent(Identity.generate(), None, state_dir=tmp_path)
    inside, overlap = [], []

    def one(reason):
        inside.append(1)
        overlap.append(len(inside))
        threading.Event().wait(0.02)
        inside.pop()
        return 0
    agent._pull = one
    ts = [threading.Thread(target=agent.pull, args=("wake",)) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert overlap == [1] * 6


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

"""What each piece may hold, and who the host serves first, are DATA per deployment (V2-891, node 3.194).

The operator's own machine and a small hosted machine are not the same host: a laptop runs other programs and a model
server next to the engine and has swap; a hosted machine runs the engine alone with no swap. So the voice, the body,
a Brain Worker and the browser each have a budget and a ceiling per deployment, the free floor is per deployment,
and the priorities (nice, OOM score) are declared — `config/resources.default.json` → `budgets`, `priorities`.

  (a) `local` and `cloud` both declare every piece, and the deployment is read from the environment (a hosted
      account, or `ZAELAR_DEPLOYMENT`);
  (b) the worker floor is the deployment's own — the same max(20 % · total, 768 MB) as before on a laptop, 200 MB on
      a hosted machine — and a policy with only the older flat keys keeps the older rule;
  (c) a worker runs at an ABSOLUTE nice (10, not the body's 5 + 10) and asks for its OOM score; raising never needs a
      privilege, so the actuator reports what the host allowed instead of raising;
  (d) the voice's own process over its ceiling is recycled only BETWEEN sessions — over the ceiling in a session,
      it waits and says so once.

Disarms (each seen red): `deployment()` always `local` → (a)/(b); `os.nice(nice)` relative in `envelope.preexec`
→ (c); drop the `live()` check in `voice_recycle.check_ceiling` → (d).
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

from nucleo.pulse import budgets, priority, voice_recycle
from nucleo.workers import envelope

ROOT = Path(__file__).resolve().parents[3]
DECLARED = json.loads((ROOT / "config/resources.default.json").read_text())
GB = 2 ** 30


def test_both_deployments_declare_every_piece(monkeypatch):
    for which in ("local", "cloud"):
        row = DECLARED["budgets"][which]
        for piece in budgets.PIECES:
            assert row[piece]["mb"] > 0 and row[piece]["ceiling_mb"] >= row[piece]["mb"], (which, piece)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("ZAELAR_DEPLOYMENT", raising=False)
    assert budgets.deployment() == "local"
    monkeypatch.setenv("ZAELAR_USER_ID", "acct-1")
    assert budgets.deployment() == "cloud"
    monkeypatch.setenv("ZAELAR_DEPLOYMENT", "local")
    assert budgets.deployment() == "local"


def test_the_voice_budget_is_the_same_small_one_everywhere():
    for which in ("local", "cloud"):
        v = budgets.budget("voice", DECLARED, which)
        assert v == {"mb": 300.0, "ceiling_mb": 400.0}


def test_the_worker_floor_is_the_deployments_own(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("ZAELAR_DEPLOYMENT", raising=False)
    assert envelope.floor(48 * GB, DECLARED) == 0.2 * 48 * GB              # a big laptop: the ratio
    assert envelope.floor(2 * GB, DECLARED) == 768 * 2 ** 20                # a small one: the reserve
    monkeypatch.setenv("ZAELAR_DEPLOYMENT", "cloud")
    assert envelope.floor(2 * GB, DECLARED) == 200 * 2 ** 20                # a hosted machine: its own floor
    flat = {"admit_free_ratio": 0.2, "voice_reserve_mb": 768}
    assert envelope.floor(2 * GB, flat) == 768 * 2 ** 20, "a policy without budgets keeps the older rule"


def test_a_worker_runs_at_an_absolute_nice_and_asks_for_its_oom_score(monkeypatch):
    got = []
    monkeypatch.setattr(os, "getpriority", lambda *_a: 5)                  # the body already runs at 5
    monkeypatch.setattr(os, "nice", lambda n: got.append(n))
    monkeypatch.setattr(envelope, "policy", lambda: {**DECLARED, "worker_nice": 10})
    envelope.preexec()()
    assert got == [5], "a worker of a body at nice 5 must land at 10, not 15"
    assert priority.targets("worker", DECLARED) == {"nice": 10, "oom_score_adj": 500}
    assert priority.targets("voice", DECLARED) == {"nice": 0, "oom_score_adj": -500}
    assert priority.targets("chromium", DECLARED)["oom_score_adj"] > priority.targets("worker", DECLARED)["oom_score_adj"]


def test_the_actuator_reports_what_the_host_allowed_and_never_raises(monkeypatch):
    def _refuse(*_a):
        raise PermissionError("not allowed")
    monkeypatch.setattr(os, "getpriority", lambda *_a: 5)
    monkeypatch.setattr(os, "setpriority", _refuse)
    out = priority.apply(0, "voice", DECLARED)
    assert out["nice"] is False and out["want"] == {"nice": 0, "oom_score_adj": -500}


class _Child:
    def __init__(self, rss, live):
        self._rss, self._live = rss, live

    def rss_mb(self):
        return self._rss

    def live(self):
        return self._live


def _app(child):
    return SimpleNamespace(state=SimpleNamespace(lk_server=child))


def test_the_voice_process_over_its_ceiling_is_recycled_only_between_sessions(monkeypatch):
    said, recycled = [], []
    monkeypatch.setattr(voice_recycle, "_emit", lambda step, text="", **x: said.append((step, x)))

    async def _recycle(_app):
        recycled.append(1)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    voice_recycle._state.pop("over_said", None)
    assert asyncio.run(voice_recycle.check_ceiling(_app(_Child(250, False)), _recycle)) == "ok"
    assert asyncio.run(voice_recycle.check_ceiling(_app(_Child(520, True)), _recycle)) == "in_session"
    assert asyncio.run(voice_recycle.check_ceiling(_app(_Child(530, True)), _recycle)) == "in_session"
    assert recycled == [] and len(said) == 1, "a live session is never cut, and the wait is said once"
    assert asyncio.run(voice_recycle.check_ceiling(_app(_Child(530, False)), _recycle)) == "recycled"
    assert recycled == [1]
    embedded = SimpleNamespace(state=SimpleNamespace(lk_server=SimpleNamespace(id="w")))
    assert asyncio.run(voice_recycle.check_ceiling(embedded, _recycle)) == "n/a"

"""What each piece may hold, and who the host serves first, are DATA per deployment (V2-891, node 3.194).

The operator's own machine and a small hosted machine are not the same host: a laptop runs other programs and a model
server next to the engine and has swap; a hosted machine runs the engine alone with no swap. So the voice, the body,
a Brain Worker and the browser each have a budget and a ceiling per deployment, the free floor is per deployment,
and the priorities (nice, OOM score) are declared — `config/resources.default.json` → `budgets`, `priorities`.

  (a) `local` and `cloud` both declare every piece, and the deployment is read from the environment (a hosted
      account, or `ZAELAR_DEPLOYMENT`);
  (b) the worker floor is the deployment's own and says what the PIECES need, never a share of the host: on a 48 GB
      laptop the declared ceilings + the reserve (~3.4 GB), so 5 GB free admits an errand with ordinary apps open; on
      a small host the ratio caps it — a 4 GB host at 600 MB free does not admit, a 2 GB host keeps the 768 MB voice
      reserve; 200 MB on a hosted machine; the host is SHORT only under the voice's ceiling + reserve (capped by the
      pause ratio), and a policy with only the older flat keys, or a block without `pieces`, keeps the older rule;
  (c) a worker runs at an ABSOLUTE nice (10, not the body's 5 + 10) and asks for its OOM score; raising never needs a
      privilege, so the actuator reports what the host allowed instead of raising;
  (d) the voice's own process over its ceiling is recycled only BETWEEN sessions — over the ceiling in a session,
      it waits and says so once.

Disarms (each seen red): `deployment()` always `local` → (a)/(b); `free_floor_mb` back to max(ratio · total, mb)
→ (b); `under_pressure` back to `pause_free_ratio` · total → (b); `os.nice(nice)` relative in `envelope.preexec`
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
        for piece in ("voice", "body", "worker", "chromium"):
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
    need = (400 + 1200 + 600 + 500 + 768) * 2 ** 20                         # the pieces' ceilings + the reserve
    assert envelope.floor(48 * GB, DECLARED) == need                        # a big laptop: what the pieces need
    assert envelope.admits(48 * GB, 5 * GB, DECLARED), "5 GB free on a 48 GB laptop runs an errand"
    assert not envelope.under_pressure(48 * GB, 4 * GB, DECLARED), "4 GB free on a 48 GB laptop is not short"
    assert envelope.under_pressure(48 * GB, 1 * GB, DECLARED), "1 GB free is short: the voice's ceiling + reserve"
    assert envelope.floor(4 * GB, DECLARED) == 0.2 * 4 * GB                 # a small host: the ratio caps the need
    assert not envelope.admits(4 * GB, 600 * 2 ** 20, DECLARED), "600 MB free on a 4 GB host holds the errand"
    assert envelope.under_pressure(4 * GB, 300 * 2 ** 20, DECLARED) and not envelope.under_pressure(
        4 * GB, 500 * 2 ** 20, DECLARED), "on a small host the older pause share (10 %) still says short"
    assert envelope.floor(2 * GB, DECLARED) == 768 * 2 ** 20                # a smaller one: the voice reserve
    unnamed = json.loads(json.dumps(DECLARED))
    for k in ("pieces", "pressure_pieces"):
        unnamed["budgets"]["local"]["free_floor"].pop(k)
    assert envelope.floor(48 * GB, unnamed) == 0.2 * 48 * GB, "a block without `pieces` keeps the older rule"
    assert envelope.under_pressure(48 * GB, 4 * GB, unnamed)
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


def test_a_misspelt_piece_is_refused_loudly_and_the_cloud_names_none():
    """2026-11-13 audit: a name in `pieces` that no piece declares fell back to 0 and LOWERED the floor in silence; and
    `pieces` in the `cloud` block were dead data (its ratio 0 caps them to nothing). Disarm (seen red): drop the
    unknown-piece check in `budgets.free_floor_mb`."""
    import pytest
    typo = json.loads(json.dumps(DECLARED))
    typo["budgets"]["local"]["free_floor"]["pieces"] = ["voice", "bdoy"]
    with pytest.raises(ValueError, match="bdoy"):
        budgets.free_floor_mb(48 * GB, typo, "local")
    assert not {"pieces", "pressure_pieces"} & set(DECLARED["budgets"]["cloud"]["free_floor"])

"""A round starts only on an engine that answers (V2-860 T0.1).

44 of the 51 INFRA rows on the scoreboard were `Connection refused` with zero turns: one batch walked case after
case against an engine that was not listening and wrote each one as its own round. The batch's first contact with
the engine (the stage reset) now tells a refused port apart: it waits a bounded time, restarts its own sandbox
ONCE, and otherwise records ONE infra row and stops. These drive the REAL `_run_batch` against a real closed
port — no fake of the probe itself.
"""
from __future__ import annotations

import socket

from tests.use_cases.e2e.agent import (config, engine_up, probe_client, report as reportmod, run as R,
                                       scenarios as SC, status as statusmod)


def _s(sid: str):
    return SC.UseCaseScenario(id=sid, locale="es", tier=2, persona_brief="p", opening_line="o",
                              success_checks="s")


def _closed_port() -> int:
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]          # closed again on exit: nothing listens there


def _batch(monkeypatch, tmp_path, ids, *, revive=None, alive_after_revive=False):
    ran, recorded = [], []
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(config, "ZAELAR_URL", f"http://127.0.0.1:{_closed_port()}")
    monkeypatch.setattr(engine_up, "WAIT_S", 0.0)
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        ran.append(scn.id) or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                               "run": {}, "verdict": {"overall": 5}}))
    monkeypatch.setattr(statusmod, "record", lambda rows, **k: recorded.extend(rows))
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    if alive_after_revive:
        state = {"up": False}
        real_reset = probe_client.hard_reset

        def reset():
            if state["up"]:
                return {}
            return real_reset()                                  # the real refused call
        monkeypatch.setattr(probe_client, "hard_reset", reset)
        monkeypatch.setattr(probe_client, "settle_after_reset",
                            lambda **k: {"clean": True, "waited_s": 0, "tasks": [], "items": []})
        monkeypatch.setattr(engine_up, "answers", lambda timeout=3.0: state["up"])

        def _revive():
            revive_calls.append(1)
            state["up"] = True
            return True
        revive = _revive
    revive_calls: list = []
    R._run_batch([_s(i) for i in ids], sandboxed=True, args_no_file=True, revive=revive)
    return ran, recorded, revive_calls


def test_a_refused_engine_records_one_infra_row_and_stops_the_walk(monkeypatch, tmp_path):
    ran, recorded, _ = _batch(monkeypatch, tmp_path, ["a", "b", "c"])
    assert ran == []                                      # no case was driven against a dead port
    assert [r["scenario"] for r in recorded] == ["a"]     # ONE row, not three
    verdict = recorded[0]["verdict"]
    assert verdict["overall"] is None and engine_up.REASON in verdict["veredicto"]
    assert verdict["veredicto"].startswith("INFRA")


def test_a_revived_sandbox_runs_the_batch(monkeypatch, tmp_path):
    ran, recorded, calls = _batch(monkeypatch, tmp_path, ["a", "b"], alive_after_revive=True)
    assert calls == [1]                                   # restarted ONCE
    assert ran == ["a", "b"]
    assert not any(engine_up.REASON in str((r.get("verdict") or {}).get("veredicto")) for r in recorded)


def test_a_reset_that_fails_for_another_reason_keeps_the_batch(monkeypatch, tmp_path):
    """Only a REFUSED port stops the walk; a broken reset on a live engine still lets the cases run."""
    def boom():
        raise RuntimeError("motor mudo")
    ran, recorded = [], []
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(probe_client, "hard_reset", boom)
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        ran.append(scn.id) or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                               "run": {}, "verdict": {"overall": 5}}))
    monkeypatch.setattr(statusmod, "record", lambda rows, **k: recorded.extend(rows))
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    R._run_batch([_s("a"), _s("b")], sandboxed=True, args_no_file=True)
    assert ran == ["a", "b"]


def test_ensure_restarts_at_most_once():
    calls = []
    out = engine_up.ensure(revive=lambda: calls.append(1) or True, wait_s=0.0,
                           probe=lambda: False, sleep=lambda *_: None)
    assert calls == [1] and engine_up.REASON in out
    assert engine_up.ensure(wait_s=0.0, probe=lambda: True, sleep=lambda *_: None) == ""

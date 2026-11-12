"""nucleo/pulse/priority.py — who the host serves first and who it gives up first, as actuators over data (V2-891).

Two levers the operating system offers to say «this process matters more»:
  · scheduling priority (`nice`): the voice 0, the body 5, a Brain Worker 10, the browser 10;
  · the out-of-memory score (`oom_score_adj`, Linux): the voice -500 (killed last), the body 0, a worker +500, the
    browser +800 (killed first) — a host that does run out kills the errand's browser, not the ear.

The values are declared in `config/resources.default.json` → `priorities.<role>`. Raising a nice value or an OOM
score never needs a privilege; LOWERING one does (root, or CAP_SYS_NICE / CAP_SYS_RESOURCE). So every actuator
tries, reports what took, and never raises: an unprivileged host keeps what it could set and says so once.
"""
from __future__ import annotations

import os
import sys

from loguru import logger

_FALLBACK = {"voice": {"nice": 0, "oom_score_adj": -500}, "body": {"nice": 5, "oom_score_adj": 0},
             "worker": {"nice": 10, "oom_score_adj": 500}, "chromium": {"nice": 10, "oom_score_adj": 800}}


def targets(role: str, pol: dict | None = None) -> dict:
    if pol is None:
        try:
            from nucleo.workers import envelope
            pol = envelope.policy()
        except Exception:  # noqa: BLE001
            pol = {}
    declared = ((pol or {}).get("priorities") or {}).get(role)
    row = declared if isinstance(declared, dict) else _FALLBACK.get(role, {})
    return {"nice": int(row.get("nice", 0)), "oom_score_adj": int(row.get("oom_score_adj", 0))}


def _threads(pid: int) -> list[int]:
    """On Linux a nice value belongs to a THREAD: this process's threads already running take it one by one."""
    path = f"/proc/{pid or 'self'}/task"
    if not sys.platform.startswith("linux") or not os.path.isdir(path):
        return [pid]
    try:
        return [int(t) for t in os.listdir(path)]
    except OSError:
        return [pid]


def set_nice(pid: int, value: int) -> bool:
    """`pid`'s nice value to `value` (0 = this process). False when the host refused (lowering needs a privilege)."""
    ok = True
    for tid in _threads(pid):
        try:
            if os.getpriority(os.PRIO_PROCESS, tid) != value:
                os.setpriority(os.PRIO_PROCESS, tid, value)
        except (OSError, AttributeError):
            ok = False
    return ok


def set_oom(pid: int, value: int) -> bool | None:
    """`pid`'s OOM score adjustment (Linux). None where there is no such thing (macOS); False when refused."""
    path = f"/proc/{pid or 'self'}/oom_score_adj"
    if not sys.platform.startswith("linux") or not os.path.exists(path):
        return None
    try:
        with open(path, "w", encoding="ascii") as fh:
            fh.write(str(int(value)))
        return True
    except OSError:
        return False


def apply(pid: int, role: str, pol: dict | None = None) -> dict:
    """Apply `role`'s declared priority to `pid`. Returns what took: `{"nice": bool, "oom_score_adj": bool|None}`."""
    t = targets(role, pol)
    out = {"role": role, "nice": set_nice(pid, t["nice"]), "oom_score_adj": set_oom(pid, t["oom_score_adj"]),
           "want": t}
    if out["nice"] is False or out["oom_score_adj"] is False:
        logger.info(f"priority: {role} (pid {pid or os.getpid()}) wanted {t} — the host allowed {out}")
    return out


def apply_self(role: str, pol: dict | None = None) -> dict:
    return apply(0, role, pol)


def preexec(role: str, pol: dict | None = None):
    """A `preexec_fn` that applies `role` in the child before it runs (raising only, so always allowed)."""
    t = targets(role, pol)

    def _apply():
        try:
            cur = os.getpriority(os.PRIO_PROCESS, 0)
            if t["nice"] > cur:
                os.nice(t["nice"] - cur)
        except OSError:
            pass
        set_oom(0, t["oom_score_adj"])
    return _apply

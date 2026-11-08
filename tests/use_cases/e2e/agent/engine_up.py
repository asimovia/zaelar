"""Is the engine under test there at all? Asked before a case's first turn, never inferred from 44 dead rounds.

Measured on the scoreboard (V2-860 T0.1): of the 51 INFRA rows since 2026-10-25, 44 read
`<urlopen error [Errno 61] Connection refused>` with zero turns used — one batch walked case after case against an
engine that was not listening, and every case was written to the shared board as its own INFRA round. The
autopsy in `run.engine_autopsy` already told ALIVE from DEAD, but only AFTER each crash.

The first contact of every case is the stage reset (`probe_client.hard_reset`). When that contact is REFUSED, this
module waits a bounded time for `/api/status`, asks the batch's `revive` (the sandbox restarts its own engine,
once; the operator's live engine and a lab agent are never restarted from here), and answers with ONE infra
reason. The batch then records that one row and stops: the remaining cases did not run, they are not rounds.
"""
from __future__ import annotations

import os
import time
import urllib.request

from . import config

#: How long a refused engine is given to come back before the case is called unmeasurable.
WAIT_S = float(os.getenv("UC_ENGINE_WAIT_S", "30"))
#: Between two probes of `/api/status`.
POLL_S = 2.0
#: The one reason a batch records when its engine is not there.
REASON = "sandbox engine not answering"


def refused(exc: BaseException) -> bool:
    """The error says nothing is listening (a connection refused), as opposed to a slow or broken answer."""
    s = f"{exc!r} {exc}".lower()
    return "refused" in s or "errno 61" in s or "errno 111" in s


def answers(timeout: float = 3.0) -> bool:
    """`/api/status` of the engine under test answers at all."""
    try:
        req = urllib.request.Request(config.ZAELAR_URL.rstrip("/") + "/api/status",
                                     headers={"User-Agent": "zaelar-uc-preflight"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(200)
        return True
    except Exception:  # noqa: BLE001 — any failure here means «not answering»
        return False


def _wait(wait_s: float, probe, sleep) -> bool:
    deadline = time.monotonic() + max(0.0, wait_s)
    while True:
        if probe():
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(POLL_S)


def ensure(*, revive=None, wait_s: float | None = None, probe=None, sleep=time.sleep) -> str:
    """'' when the engine answers (now, after the bounded wait, or after ONE `revive`); else the infra reason.

    `revive` is a callable the batch owns — it returns True when it brought the engine back. It is called at most
    once; a revive that raises counts as not revived."""
    probe = probe or answers
    wait_s = WAIT_S if wait_s is None else wait_s
    if _wait(wait_s, probe, sleep):
        return ""
    if revive is not None:
        try:
            if revive() and _wait(wait_s, probe, sleep):
                return ""
        except Exception as e:  # noqa: BLE001 — a failed restart is reported, never raised over the batch
            print(f"  ⚠️ the engine restart failed: {e}")
        return f"{REASON} at {config.ZAELAR_URL} (waited {wait_s:.0f}s, restarted once)"
    return f"{REASON} at {config.ZAELAR_URL} (waited {wait_s:.0f}s)"

"""nucleo/pulse/starvation.py — a starved CPU is not a dead worker (V2-872).

Measured on a small shared-CPU host: after a cold boot burned the CPU quota, the host was throttled — `/proc/stat`
read user+sys 152 s against steal 654 s after 17 min of uptime — and the voice stack said so in its own words (the VAD
«slower than realtime», LiveKit «job executor is unresponsive» ×8 in seconds). The heartbeat counted those marks as a
degraded engine and recycled the worker over a live session; a recycle cannot give the host CPU back, it only adds a
cold start.

So between two beats the heartbeat samples what the host says about its CPU:
  * `/proc/stat`, first `cpu` line (user nice system idle iowait irq softirq steal, in ticks) → the window's STEAL
    SHARE = steal / (busy + idle + steal): the time the hypervisor gave our vCPUs to someone else;
  * `/sys/fs/cgroup/cpu.stat`, when present (`nr_throttled`, `throttled_usec`) → the ms the cgroup was throttled.
Without those files (macOS, a laptop) the window reads unknown and nothing changes. `starved()` is the pure
classification, the clock and the numbers as arguments; `tick()` is the sampling, kept here (not in
`homeostasis_policy`, whose functions are pure by contract) with the one piece of state it needs: the previous sample.
The last window is what the `pressure` block reports (`cpu_steal_pct`, `cpu_throttled_ms`).
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

_PROC_STAT = "/proc/stat"
_CGROUP_STAT = "/sys/fs/cgroup/cpu.stat"

_state: dict = {"prev": None, "window": None, "open": False}   # a state record: the last sample, the last window, open = a starved episode already told


def read_proc_stat(path: str = _PROC_STAT) -> dict | None:
    """The host's cumulative CPU ticks: `{busy, idle, steal}`, or None where there is no `/proc/stat`."""
    try:
        with open(path, encoding="ascii") as fh:
            for line in fh:
                parts = line.split()
                if parts and parts[0] == "cpu":
                    v = ([int(x) for x in parts[1:9]] + [0] * 8)[:8]   # an old kernel has no steal column
                    user, nice, system, idle, iowait, irq, softirq, steal = v[:8]
                    return {"busy": user + nice + system + irq + softirq, "idle": idle + iowait, "steal": steal}
    except (OSError, ValueError):
        return None
    return None


def read_cgroup(path: str = _CGROUP_STAT) -> dict | None:
    """The cgroup's cumulative throttling: `{nr_throttled, throttled_usec}`, or None where the file is absent."""
    try:
        with open(path, encoding="ascii") as fh:
            kv = dict(line.split()[:2] for line in fh if len(line.split()) >= 2)
        if "nr_throttled" not in kv or "throttled_usec" not in kv:
            return None
        return {"nr_throttled": int(kv["nr_throttled"]), "throttled_usec": int(kv["throttled_usec"])}
    except (OSError, ValueError):
        return None


def window(prev: dict | None, cur: dict | None) -> dict:
    """The difference between two samples: `steal_pct` and `throttled_ms` (None = unknown). Pure."""
    out: dict = {"steal_pct": None, "throttled_ms": None, "nr_throttled": None}
    if not prev or not cur:
        return out
    a, b = prev.get("cpu"), cur.get("cpu")
    if a and b:
        d = {k: b[k] - a[k] for k in ("busy", "idle", "steal")}
        total = d["busy"] + d["idle"] + d["steal"]
        if total > 0 and min(d.values()) >= 0:
            out["steal_pct"] = round(100.0 * d["steal"] / total, 1)
    a, b = prev.get("cg"), cur.get("cg")
    if a and b and b["throttled_usec"] >= a["throttled_usec"]:
        out["throttled_ms"] = round((b["throttled_usec"] - a["throttled_usec"]) / 1000)
        out["nr_throttled"] = max(0, b["nr_throttled"] - a["nr_throttled"])
    return out


def starved(win: dict, steal_pct_starved: float) -> bool | None:
    """True when the window's steal share is over the threshold or the cgroup throttled in it; False when the numbers
    were read and are under; None when nothing could be read (the host says nothing — the heartbeat changes nothing)."""
    steal, throttled = win.get("steal_pct"), win.get("throttled_ms")
    if steal is None and throttled is None:
        return None
    return bool((steal is not None and steal > float(steal_pct_starved))
                or (throttled is not None and (throttled > 0 or (win.get("nr_throttled") or 0) > 0)))


def tick(read=None) -> dict:
    """Sample now, keep the sample for the next beat, and return the window since the previous one."""
    cur = read() if read is not None else {"cpu": read_proc_stat(), "cg": read_cgroup()}
    win = window(_state["prev"], cur)
    _state["prev"], _state["window"] = cur, win
    return win


def last_window() -> dict:
    """The last window the heartbeat read (empty before the second beat)."""
    return dict(_state["window"] or {})


def read(steal_pct_starved: float) -> tuple[dict, bool | None]:
    """The heartbeat's reading: the window since the last beat and its classification. A window read under the
    threshold closes the episode (the next starved one is told again). Never raises."""
    try:
        win = tick()
    except Exception as e:  # noqa: BLE001
        log.warning("starvation: CPU sample failed: %s", e)
        return {}, None
    verdict = starved(win, steal_pct_starved)
    if verdict is False:
        _state["open"] = False
    return win, verdict


async def report(win: dict, marks: list, emit) -> None:
    """The window's LiveKit `marks` were the host: they are dropped, the event carries the numbers on every starved
    beat, and ONE notice in his language per episode — on screen only, never spoken (V2-768: a spoken health line
    opens the reply window)."""
    n, marks[:] = len(marks), []
    emit("starved", "CPU starved — the voice marks are the host, not the worker; no recycle",
         extra={"kind_diag": "starved", "cat": "voice", "marks": n, "steal_pct": win.get("steal_pct"),
                "throttled_ms": win.get("throttled_ms"), "nr_throttled": win.get("nr_throttled")})
    if _state["open"]:
        return
    _state["open"] = True
    try:
        from i18n import langs
        from nucleo.pulse import notices
        line = str(langs.words("alerts.cpu_starved", default="cpu_starved"))
        await notices.notify("zaelar", line, key=f"cpu_starved:{time.time_ns()}", kind="info", speak=False,
                             push_=False)
    except Exception as e:  # noqa: BLE001 — the event above still stands
        log.warning("starvation: cpu_starved notice not delivered (%r)", e)

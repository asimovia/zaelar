"""At boot, the queue takes back what a restart left (INI-078 spec §1 and §3).

  · his live worker commissions written before the queue existed become tasks of it (`owner='worker'`, a number, and
    their creation order) — once: a row already in the queue is left as it is;
  · a task that was RUNNING when the process ended goes back to the head of its lane (`back`, by the pulse) — nothing
    says «interrupted by a restart»: it is the same task, resumed;
  · every worker task still pending is relaunched on its own row (its brief reused, its sheet kept), and waits for its
    turn like any other; a task waiting for his answer stays waiting — his answer resumes it.
"""
from __future__ import annotations

from loguru import logger

from nucleo import queue as _q

#: what a worker commission's row is: his (visible), now, alive — the rows the queue adopts at boot
_LIVE = ("pending", "running", "waiting")


def adopted() -> list[str]:
    """His live worker rows that are not tasks of the queue yet, adopted in their creation order. Their ids."""
    from nucleo.circuit import ledger
    out = []
    for r in ledger.store().tasks_where(states=_LIVE, modes=("now",), visible_only=True, limit=500):
        if r.get("owner") or not ledger.is_visible(kind=str(r.get("kind") or ""), origin=str(r.get("origin") or "voz")):
            continue
        tid = _q.add("worker", str(r.get("title") or ""), goal=str(r.get("goal") or ""), kind=str(r.get("kind") or ""),
                     origin=str(r.get("origin") or "voz"), trace=str(r.get("trace_id") or ""), task_id=str(r["id"]))
        if tid and r.get("state") == "waiting":       # it was waiting for him: it still is
            _q.signal(tid, "start", by="pulse")
            _q.signal(tid, "wait", by="pulse", ask=str(r.get("ask") or ""), ask_id=str(r.get("ask_id") or ""),
                      waiting_for=str(r.get("waiting_for") or ""), deadline=r.get("deadline"))
        if tid:
            out.append(tid)
    return out


def at_boot(*, schedule: bool = True, delay: float | None = None) -> dict:
    """Adopt, put back, relaunch. Never raises: a boot that could not take the queue back still starts."""
    plan = {"adopted": [], "back": [], "relaunched": []}
    try:
        plan["adopted"] = adopted()
        for r in _q._store().queue_rows("worker"):
            if r.get("state") == _q.RUNNING and _q.signal(str(r["id"]), "back", by="pulse"):
                plan["back"].append(str(r["id"]))
        pending = [r for r in _q._store().queue_rows("worker") if r.get("state") == _q.PENDING]
        plan["relaunched"] = [str(r["id"]) for r in pending]
        if schedule and pending:
            from nucleo.pulse import rehydrate
            rehydrate._schedule([{"goal": str(r.get("goal") or r.get("title") or ""), "uid": str(r["id"]),
                                  "kind": str(r.get("kind") or "generic")} for r in pending],
                                rehydrate.RESUME_DELAY_S if delay is None else float(delay))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"queue: the boot could not take the queue back ({e!r})")
    if any(plan.values()):
        logger.info(f"queue at boot: {len(plan['adopted'])} adopted, {len(plan['back'])} back, "
                    f"{len(plan['relaunched'])} relaunched")
    return plan

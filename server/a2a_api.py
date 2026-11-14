"""The A2A network's door in the engine (V2-866): two routes and one thread, all asleep until he switches it on.

    POST /api/a2a/wake    a wake push signed by the network key (pinned at boot) → one pull · else 401, nothing
    GET  /api/a2a/status  loopback or `A2A_API_TOKEN` → the agent's status

OFF by default (`config.v2` section `a2a`, `enabled`): no key is read, no thread starts, no byte leaves, and both
routes answer 404 as if they were not there. On, `start()` builds the agent over the engine's seams
(`server/a2a_wiring.py`), pins the network key and ticks the jobs every `TICK_S` on a daemon thread."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter()

TICK_S = 30.0
_state: dict = {"agent": None, "jobs": None, "gate": None, "thread": None, "stop": None}


def enabled() -> bool:
    try:
        from config import v2
        return bool(v2.get("a2a").get("enabled"))
    except Exception:                                       # noqa: BLE001 — an unreadable config is OFF
        return False


def build():
    """The agent and its jobs over the engine's seams. No network call."""
    import a2a
    from config import v2
    from . import a2a_wiring as w
    items = a2a.default_items(busy=w.busy, public_profile=w.public_profile)
    agent = a2a.from_network(items=items, grant_store=w.RulesGrantStore(), policy=w.policy,
                             scan_outbound=w.scan_outbound, display_name=str(v2.get("a2a").get("display_name") or ""))
    return agent, a2a.Jobs(agent, contacts=w.contacts)


def start() -> bool:
    """Idempotent; never raises; does nothing while A2A is off."""
    if _state["thread"] is not None or not enabled():
        return False
    try:
        import a2a
        a2a.attach_bus()
        agent, jobs = build()
        try:
            key = agent.mailbox.server_key().get("pubkey")
        except Exception as e:                              # noqa: BLE001 — unpinned: every wake is refused
            logger.warning(f"a2a: network key not pinned ({type(e).__name__}); wake pushes are refused")
            key = None
        _state.update(agent=agent, jobs=jobs, gate=a2a.WakeGate(key))
    except Exception as e:                                  # noqa: BLE001 — voice and chat never depend on A2A
        logger.warning(f"a2a start failed (voice/chat unaffected): {type(e).__name__}: {e}")
        return False
    stop_ev = threading.Event()

    def run():
        while not stop_ev.wait(TICK_S):
            try:
                jobs.tick()
            except Exception as e:                          # noqa: BLE001 — one bad tick never ends the loop
                logger.debug(f"a2a tick: {type(e).__name__}")
    _state.update(stop=stop_ev, thread=threading.Thread(target=run, name="a2a-jobs", daemon=True))
    _state["thread"].start()
    return True


def stop() -> None:
    if _state["stop"] is not None:
        _state["stop"].set()
    _state.update(thread=None, stop=None)


def contact_event(cid: str) -> None:
    """A contact was created or edited: one debounced lookup (a no-op while A2A is off)."""
    if _state["jobs"] is not None:
        _state["jobs"].contact_event(str(cid))


def _off() -> JSONResponse:
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/api/a2a/wake")
async def wake(request: Request):
    if _state["jobs"] is None:
        return _off()
    body = (await request.body()).decode("utf-8", "replace")
    code, out = _state["gate"].handle(_state["jobs"], dict(request.headers), body)
    return JSONResponse(out, status_code=code)


@router.get("/api/a2a/status")
async def status(request: Request):
    import a2a
    if _state["agent"] is None:
        return _off()
    host = request.client.host if request.client else ""
    if not a2a.status_allowed(host, dict(request.headers)):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return _state["agent"].status()

"""The A2A network's door in the engine (V2-866): two routes and one thread, all asleep until he switches it on.

    POST /api/a2a/wake    a wake push signed by the network key (pinned at boot) → one pull · else 401, nothing
    GET  /api/a2a/status  loopback or `A2A_API_TOKEN` → the agent's status
    GET  /api/a2a/network same access → relationships + grants, pending cards, recent activity (the Network view)
    POST /api/a2a/cards/{id} {yes} same access → the owner's answer to a consent card (`server/a2a_cards.py`)

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
_state: dict = {"agent": None, "jobs": None, "gate": None, "thread": None, "stop": None, "cards": None}
CONTACT_TOPIC = "contact.saved"      # published by the contacts widget on a write (`widgets/contactos/data.py`)


def enabled() -> bool:
    try:
        from config import v2
        return bool(v2.get("a2a").get("enabled"))
    except Exception as exc:                                       # noqa: BLE001 — an unreadable config is OFF
        logger.debug("a2a: server/a2a_api.py:enabled failed: {!r}", exc)
        return False


def build():
    """The agent and its jobs over the engine's seams. No network call."""
    import a2a
    from config import v2
    from a2a.store import default_state_dir
    from . import a2a_wiring as w
    from .a2a_cards import Cards
    items = a2a.default_items(busy=w.busy, public_profile=w.public_profile)
    w.declare_widget_items(items)
    cards = Cards(default_state_dir())
    agent = a2a.from_network(items=items, grant_store=w.RulesGrantStore(), policy=w.policy,
                             scan_outbound=w.scan_outbound, display_name=str(v2.get("a2a").get("display_name") or ""),
                             asker=cards.asker, on_message=cards.on_message)
    cards.agent = agent
    _state["cards"] = cards
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
        a2a.set_runtime(agent, jobs)
        import bus
        bus.add_sink(_on_bus)
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
    try:
        import a2a
        import bus
        a2a.set_runtime(None, None)
        bus.remove_sink(_on_bus)
    except Exception as exc:                                       # noqa: BLE001
        logger.debug("a2a: server/a2a_api.py:stop failed: {!r}", exc)
        pass


def _on_bus(rec: dict) -> None:
    """The contacts widget saved a contact → one debounced lookup (item 7). The widget only publishes a topic."""
    if rec.get("topic") == CONTACT_TOPIC and isinstance(rec.get("payload"), dict):
        contact_event(str(rec["payload"].get("cid") or ""))


def contact_event(cid: str) -> None:
    """A contact was created or edited: one debounced lookup (a no-op while A2A is off)."""
    if _state["jobs"] is not None and cid:
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


def _allowed(request: Request) -> bool:
    import a2a
    host = request.client.host if request.client else ""
    return a2a.status_allowed(host, dict(request.headers))


@router.get("/api/a2a/network")
async def network(request: Request):
    """The Network view's one read: relationships with their grants, the pending cards, the recent rows."""
    from a2a import events
    if _state["agent"] is None:
        return _off()
    if not _allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    st = _state["agent"].status()
    recent = [{k: r.get(k) for k in ("op", "cid", "dir", "ok", "ts", "label", "item")} for r in events.recent(limit=30)]
    return {"relationships": st["relationships"], "cards": _state["cards"].pending() if _state["cards"] else [],
            "recent": recent, "items": [i.card() for i in _state["agent"].items.all()]}


@router.post("/api/a2a/cards/{card_id}")
async def answer_card(card_id: str, request: Request):
    if _state["cards"] is None:
        return _off()
    if not _allowed(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:                                       # noqa: BLE001
        body = {}
    out = _state["cards"].answer(card_id, bool(body.get("yes")))
    return JSONResponse(out, status_code=200 if out.get("ok") else 409)

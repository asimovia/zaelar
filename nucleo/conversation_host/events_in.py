"""The door of the world's events into the conversation manager (R-2, E7d-2): an event the router already ROUTED
(`nucleo/events/pump.publish`) enters the account's conversation as an EVENT envelope — its source's authority, never
his — and runs there, after his words, by the host's `Events` door, which obeys the route by the one body that obeys it
(`pump.obey`) on the engine's loop. With the manager off for the account, nothing is given and the pump obeys it as
before; a conversation that cannot open obeys it the old way too (the line's fallback).

What enters is plain data — the event's topic, source, text and declared fields, and the route's verdict; the route's
full record (a waiting row, the rules, a claimant's own record) stays here, by the event's id, for its door.
"""
from __future__ import annotations

import threading
import time
import uuid

from typing import Any

#: the routes given to the conversation, by event id, until their door obeys them: (event, route, when)
_GIVEN: dict[str, tuple[dict, dict, float]] = {}
_lock = threading.Lock()
#: what of an event enters the envelope as its declared fields (plain values only)
_PLAIN = (str, int, float, bool)
#: the door's word for what was done, by the route's verdict
DONE = {"resume": "resumed", "stream": "streamed"}


def _on() -> bool:
    try:
        from nucleo.conversation_host import switch
        return switch.on()
    except Exception:  # noqa: BLE001 — unreadable switch: the pump obeys, as before
        return False


def envelope(ev: dict, r: dict, event_id: str, now_ms: int):
    from conversation import envelopes as E
    from conversation.types import EnvelopeKind
    from nucleo.conversation_host import boot
    declared = ev.get("fields") if isinstance(ev.get("fields"), dict) else {}
    fields = {k: v for k, v in {**declared, "key": ev.get("key")}.items() if isinstance(v, _PLAIN) and v != ""}
    route = {k: str(r[k]) for k in ("as", "by", "task") if r.get(k) is not None}
    body = E.EventBody(event_id, str(ev.get("origin") or ""), str(declared.get("platform") or ""),
                       str(ev.get("text") or "")[:4000], fields, route)
    return E.make(EnvelopeKind.EVENT, body, producer="event:router", producer_id=event_id, account=boot.account(),
                  onset_ms=now_ms, sealed_ms=now_ms)


def give(ev: dict, r: dict, now: float | None = None) -> bool:
    """Hand a routed event to the conversation manager. False when the manager is off for the account: the caller
    obeys it then."""
    if not _on():
        return False
    from nucleo.conversation_host import entry
    from nucleo.events import once
    now = time.time() if now is None else now
    event_id = str(once.key_of(ev) or "") or f"ev_{uuid.uuid4().hex[:12]}"
    with _lock:
        _GIVEN[event_id] = (ev, r, now)
    env = envelope(ev, r, event_id, int(now * 1000))

    def deliver(conv) -> None:
        conv.give(env)

    def fallback() -> None:                  # the conversation never opened: the route is obeyed as before
        from nucleo.events import pump
        with _lock:
            got = _GIVEN.pop(event_id, None)
        if got is not None:
            pump.obey(*got)

    deliver.fallback = fallback
    entry._hand(deliver)
    return True


class HostEvents:
    """The `Events` port: an event's route obeyed by `pump.obey`, on the engine's loop where its doors live."""

    async def run(self, account: str, env: Any) -> str:
        from nucleo.conversation_host.acts_widget import _on_engine_loop
        from nucleo.events import pump
        with _lock:
            got = _GIVEN.pop(str(env.body.event_id), None)
        if got is None:                      # a route this process never held (a restart): nothing to obey
            return "nothing"
        ev, r, when = got

        async def obey() -> None:
            pump.obey(ev, r, when)
        await _on_engine_loop(obey())
        return DONE.get(str(r.get("as") or ""), "nothing")

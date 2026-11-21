"""The door of the world's events into the conversation manager (R-2, E7d-2): an event the router already ROUTED
(`nucleo/events/pump.publish`) enters the account's conversation as an EVENT envelope — its source's authority, never
his — and runs there, after his words, by the host's `Events` door, which obeys the route by the one body that obeys it
(`pump.obey`) on the engine's loop. When the manager may not run now, nothing is given and the pump obeys the route
itself, with no conversation; a conversation that cannot open hands it to `pump.obey` too (the line's fallback). The
route and `pump.obey` are the events' own body, not the old turn.

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
#: the route of an event whose work its source hands in with it (a peer's turn on a cluster): the door runs it
WORK = "work"
#: the works handed in with their events, by event id: (the work's coroutine factory, the future its source awaits)
_WORKS: dict[str, tuple] = {}


def _on() -> bool:
    try:
        from nucleo.conversation_host import switch
        return switch.on()
    except Exception as e:  # noqa: BLE001 — unreadable switch: the pump obeys, as before, and the log says why
        __import__("logging").getLogger("zaelar.conversation_host").debug(f"events_in: switch unread ({e!r})")
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
    """Hand a routed event to the conversation manager. False when the manager may not run now: the caller obeys the
    route itself then (`pump.obey`)."""
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


async def run_as_event(origin: str, text: str, work, *, fields: dict | None = None, timeout_s: float = 150.0):
    """A source that has its own WORK to do for an event (a peer's turn on a cluster, R-2): with the manager on, the
    event enters the conversation and the work runs there, after his words, by the `Events` door — its result comes
    back here; off, or when the conversation cannot open, the work runs here as before. `work()` makes the coroutine."""
    import asyncio
    import concurrent.futures
    from nucleo import events
    ev = events.event(origin, text=text, **(fields or {}))
    if not _on():
        return await work()
    event_id = f"ev_{uuid.uuid4().hex[:12]}"
    done: concurrent.futures.Future = concurrent.futures.Future()
    with _lock:
        _WORKS[event_id] = (work, done)
    from nucleo.conversation_host import entry
    env = envelope(ev, {"as": WORK}, event_id, int(time.time() * 1000))

    def deliver(conv) -> None:
        conv.give(env)

    def fallback() -> None:                  # the conversation never opened: the work runs where it was asked
        with _lock:
            _WORKS.pop(event_id, None)
        done.set_result(_HERE)

    deliver.fallback = fallback
    entry._hand(deliver)
    got = await asyncio.wait_for(asyncio.wrap_future(done), timeout=timeout_s)
    if got is _HERE:
        return await work()
    if isinstance(got, BaseException):
        raise got
    return got


_HERE = object()          # the fallback's answer: run the work where it was asked


class HostEvents:
    """The `Events` port: an event's route obeyed by `pump.obey`, on the engine's loop where its doors live."""

    async def run(self, account: str, env: Any) -> str:
        from nucleo.conversation_host.acts_widget import _on_engine_loop
        from nucleo.events import pump
        if (env.body.route or {}).get("as") == WORK:
            return await _work(str(env.body.event_id))
        with _lock:
            got = _GIVEN.pop(str(env.body.event_id), None)
        if got is None:                      # a route this process never held (a restart): nothing to obey
            return "nothing"
        ev, r, when = got

        async def obey() -> None:
            pump.obey(ev, r, when)
        await _on_engine_loop(obey())
        return DONE.get(str(r.get("as") or ""), "nothing")


async def _work(event_id: str) -> str:
    """The work an event's source handed in, STARTED here — a peer's turn can take minutes and the manager never waits
    on it: his words come first. Its result (or its failure) goes back to the source when it ends."""
    import asyncio
    with _lock:
        got = _WORKS.pop(event_id, None)
    if got is None:                          # a work this process never held (a restart): its source is gone
        return "nothing"
    work, done = got

    async def run() -> None:
        try:
            done.set_result(await work())
        except BaseException as e:  # noqa: BLE001 — the failure is the source's to handle: it goes back
            done.set_result(e)
    _STARTED.add(task := asyncio.ensure_future(run()))
    task.add_done_callback(_STARTED.discard)
    return "started"


_STARTED: set = set()                        # the works in course, kept alive until they end

"""The questions only ONE door reads are asked AT that door, merged into the turn's brief (V2-887 step 8).

Measured 2026-11-12: the turn's one Jev trip asked 16 questions (21.6k chars) with nothing open, and six of them were
read by a single door each, on a minority of turns — how many acts his words ask (read only after a door ran an
act), what an errand would do in the world, which kind of worker it needs and whether it asks for a capability no card
declares (read only at the errand portal), which channel he named (read only where a message leaves) and whether he
renames the assistant (read only after the model called `set_style_directive`). Every turn paid for them; the
whisperer read a brief a third longer than it needed.

So each of those questions belongs to a DOOR (`DOORS`), and the door asks it when it is reached. The precondition is
always something the engine DID — a model call, a launch, an act that leaves, a parked directive — never his words.
The trip runs on its own thread (`fire`, never on the voice loop) and its verdicts are MERGED into the same brief
handle, so every reader keeps reading `verdicts.read(brief, key, …)` exactly as before: a door verdict still in
flight reads as the reader's fallback and says so (`jev read … in_flight`). A door that can wait (an async close, a
worker's exit thread) waits for it boundedly (`landed`, `landed_sync`); the voice loop never does.
"""
from __future__ import annotations

import importlib
import threading

from loguru import logger

#: Which door asks which question: `{door: ((owner module, key constant, question builder(ctx)), …)}`. The owner of
#: the reader stays the one place that names the key and words the question, as in `brief.QUESTIONS`.
DOORS = dict(
    # a model call was made: whether his words asked for several acts (read when the turn's doors ran exactly one)
    call=(("nucleo.turn.acts_asked", "KEY", lambda m, _c: m.question()),),
    # an errand is launched: its consent class, its kind of worker, a capability no card declares
    portal=(("nucleo.acts.errand", "CLASS_KEY", lambda m, _c: m.class_question()),
            ("nucleo.request.kind", "KEY", lambda m, _c: m.question()),
            ("nucleo.flash.capability_gap", "KEY", lambda m, c: m.question(c.get("open_ids")))),
    # an act that leaves the machine is at its exit: the channel he named for it
    send=(("nucleo.acts.message_channel", "KEY", lambda m, _c: m.question()),),
    # the model called `set_style_directive`: whether he renames the assistant or changes when it listens
    rename=(("nucleo.turn.identity", "KEY", lambda m, _c: m.question()),),
)
#: The default bound a door that can wait gives its trip (the same budget the route gives the brief, `route_by_verdict`).
WAIT_S = 1.5


def keys(door: str | None = None) -> list[str]:
    """The keys a door asks (every door's when `door` is None), in table order."""
    rows = DOORS.get(door, ()) if door else [r for d in DOORS.values() for r in d]
    return [str(getattr(importlib.import_module(mod), name)) for mod, name, _q in rows]


def door_of(key: str) -> str:
    """The door that asks `key`, "" when the turn's brief asks it."""
    return next((d for d in DOORS if key in keys(d)), "")


def _questions(handle: dict, door: str) -> dict:
    """The door's questions this handle has not answered yet, built from what the brief recorded (its open cards)."""
    have = (handle.get("result") or {}) if isinstance(handle.get("result"), dict) else {}
    ctx = {"open_ids": list(handle.get("open_ids") or []), "operator_text": str(handle.get("judged") or "")}
    qs: dict = {}
    for mod, name, build in DOORS.get(door, ()):
        try:
            m = importlib.import_module(mod)
            key = str(getattr(m, name))
            if key in have:
                continue
            q = build(m, ctx)
            if q:
                qs[key] = q
        except Exception as e:  # noqa: BLE001 — one question that cannot be built never costs the others
            logger.debug(f"brief_doors: {door} question {mod}.{name} not built — {e!r}")
    return qs


def fire(handle, door: str):
    """Ask the door's questions about the sentence the brief judged, on their own thread, merged into `handle` when
    they land. Returns the door's event (set when merged), or None when there is nothing to ask (no brief, no
    sentence, Jev off, every answer already there). Never blocks, never raises; a door fires once per handle."""
    try:
        if not isinstance(handle, dict) or door not in DOORS:
            return None
        doors = handle.setdefault("_doors", {})
        if door in doors:
            return doors[door]
        said = str(handle.get("judged") or "").strip()
        from nucleo import jev
        if not said or not jev.enabled():
            return None
        qs = _questions(handle, door)
        if not qs:
            return None
        ev = threading.Event()
        doors[door] = ev
        handle["_pending"] = set(handle.get("_pending") or ()) | set(qs)
        threading.Thread(target=_ask, args=(handle, door, said, qs, ev), name=f"jev-door-{door}", daemon=True).start()
        return ev
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"brief_doors: {door} not fired — {e!r}")
        return None


def _ask(handle: dict, door: str, said: str, qs: dict, ev: threading.Event) -> None:
    got = None
    try:
        from nucleo import jev
        got = jev.choose_many_sync(said, qs, question_id=f"turn-brief/{door}")
        main = handle.get("event")
        if main is not None and not main.is_set():     # merged into the brief's own result, so it waits for it
            main.wait(jev._timeout_s() + 1.0)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"brief_doors: {door} trip failed — {e!r}")
    try:
        if got:
            base = handle.get("result") if isinstance(handle.get("result"), dict) else {}
            # a NEW dict: a reader iterating the old one never sees it change under it
            handle["result"] = {**base, **{k: v for k, v in got.items() if k in qs}}
    finally:
        handle["_pending"] = set(handle.get("_pending") or ()) - set(qs)
        ev.set()


async def landed(handle, door: str, wait_s: float = WAIT_S, *, ask: bool = True) -> bool:
    """For an async door: fire it (unless `ask` is False — then only a door already fired is waited for) and wait for
    its verdicts at most `wait_s`, OFF the loop. True when they are in the handle."""
    ev = fire(handle, door) if ask else ((handle or {}).get("_doors") or {}).get(door) if isinstance(handle, dict) else None
    if ev is None:
        return False
    if not ev.is_set():
        import asyncio
        try:
            await asyncio.to_thread(ev.wait, max(0.0, wait_s))
        except Exception as e:  # noqa: BLE001 — an unawaitable door reads as in flight
            logger.debug(f"brief_doors: {door} not awaited — {e!r}")
    return ev.is_set()


def landed_sync(handle, door: str, wait_s: float = WAIT_S) -> bool:
    """For a door that runs on its own thread (a worker's exit): fire it and wait at most `wait_s`. On an event loop
    it only fires — a blocking wait would stall it."""
    ev = fire(handle, door)
    if ev is None:
        return False
    if not ev.is_set() and not _on_the_loop():
        ev.wait(max(0.0, wait_s))
    return ev.is_set()


def keep(handle, reading) -> None:
    """Copy the door verdicts a revived handle gathered back into the carried reading it was revived from, so the
    next exit of the same task reads them without a second trip."""
    try:
        res = (handle or {}).get("result") if isinstance(handle, dict) else None
        if isinstance(reading, dict) and isinstance(reading.get("result"), dict) and isinstance(res, dict):
            for k in keys():
                if k in res and k not in reading["result"]:
                    reading["result"][k] = res[k]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"brief_doors: reading not kept — {e!r}")


def _on_the_loop() -> bool:
    import asyncio
    return asyncio._get_running_loop() is not None

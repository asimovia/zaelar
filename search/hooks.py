"""search/hooks.py — the service's few outward calls, as SEAMS the host wires at boot (V2-782 T5.1).

`search/` never imports `nucleo/flash` or `voice`: the turn calls the service, the service never calls the turn
(`tests/search/unit/test_the_search_service_owes_the_turn_nothing.py` is the ratchet). Two things the old
modules did reach for are kept as callables the server sets in its lifespan (`server/boot_halves.py`):

  · `on_chain_failure(kind, detail)` — lights the operator's status light (`voice.health_state.record("search", …)`
    in the engine; nothing in a standalone process).
  · `emit(family, label, **extra)` — the observability bus (`voice.observer.emit`), so the service's own rows
    (route chosen, provider answered) land on the timeline when it runs inside the engine.
  · `room(what)` — an async context manager around a Chromium launch (`nucleo.workers.room.room_for`, V2-867 F2):
    in the engine the launch waits for room on the host, pausing the newest worker; alone it launches at once.

Unset, every seam is a no-op: the service works alone, which is the point of making it a service.
"""
from __future__ import annotations

import contextlib
from typing import AsyncContextManager, Callable

from loguru import logger

on_chain_failure: Callable[[str, str], None] | None = None
emit: Callable[..., None] | None = None
#: The host's declared resource policy (`nucleo.workers.envelope.policy` in the engine): `browser_bg_wait_s` lives there.
policy: Callable[[], dict] | None = None
#: The host's room for a heavy launch (`nucleo.workers.room.room_for` in the engine, V2-867 F2).
room: Callable[[str], AsyncContextManager] | None = None


def declared(key: str, default: float) -> float:
    """One number of the host's declared policy, or `default` when the service runs alone."""
    try:
        return float((policy() if policy is not None else {}).get(key, default))
    except Exception as e:  # noqa: BLE001 — an unreadable policy keeps the default
        logger.debug(f"search.hooks: policy unreadable ({e!r})")
        return default


def chain_failed(kind: str, detail: str) -> None:
    if on_chain_failure is None:
        return
    try:
        on_chain_failure(kind, detail)
    except Exception as e:  # noqa: BLE001 — a status light must never take a search down
        logger.debug(f"search.hooks: the failure hook raised ({e!r})")


def note(family: str, label: str, **extra) -> None:
    if emit is None:
        return
    try:
        emit(family, label, **extra)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"search.hooks: the emit hook raised ({e!r})")


def room_for(what: str) -> AsyncContextManager:
    """The host's room for a launch of `what`, or an empty context when the service runs alone."""
    if room is None:
        return contextlib.nullcontext()
    return room(what)

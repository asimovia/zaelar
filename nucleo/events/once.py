"""nucleo/events/once.py — an arriving message is routed ONCE, across processes (V2-872 F2).

A source re-delivers: a mailbox hands over again what is still unread after a restart, a messaging bridge replays
what arrived while it was offline. The router obeys what it is given — a waiting row is resumed, a subscribed rule
starts its stream — so a re-delivered message would resume the same row or run the same rule twice. Deduping where
each source reconnects is a rule every source has to remember; this is the one door every arrival passes instead.

The key is what the source declares about the item itself — `<platform>:<chat>:<message id>`, the chat because some
platforms number messages per conversation — so an event without a message
id (a cron's job, a worker's end) is never deduped here. The ledger is durable (the engine's key-value table) and
bounded (`CAP`, oldest out): the only message that could pass twice is one older than the last `CAP` arrivals.
"""
from __future__ import annotations

from loguru import logger

KEY = "events:routed"
CAP = 2000


def key_of(ev: dict) -> str:
    """`<platform>:<chat>:<message id>` for an arriving message, "" for anything else."""
    f = (ev or {}).get("fields") or {}
    mid, platform = str(f.get("message") or "").strip(), str(f.get("platform") or "").strip()
    return f"{platform}:{str(f.get('chat') or '').strip()}:{mid}" if mid and platform else ""


def _kv():
    from memory import api as memory
    return memory


def _load() -> list[str]:
    """Read fresh each time (a few KB, once per arriving message): no process cache to drift from the table."""
    try:
        got = _kv().kv_get(KEY) or []
        return [str(k) for k in got] if isinstance(got, list) else []
    except Exception as e:  # noqa: BLE001 — unreadable: nothing is known to be routed
        logger.debug(f"events.once: ledger unreadable: {e!r}")
        return []


def first(ev: dict) -> bool:
    """True the first time this message is seen (and records it); False for a re-delivery. True for a non-message."""
    k = key_of(ev)
    if not k:
        return True
    keys = _load()
    if k in keys:
        return False
    keys.append(k)
    del keys[:-CAP]
    try:
        _kv().kv_set(KEY, keys)
    except Exception as e:  # noqa: BLE001 — not recorded: a later re-delivery may route once more
        logger.debug(f"events.once: ledger not written: {e!r}")
    return True

"""observability/log_mask.py — the server log wears the same mask as the stored events (V2-875 / INI-063 D13).

Every persisted observability event goes through `observability.pii.tag_obj` when the person's `obfuscate` switch is on
(`observability/persist.py`). The process log (`loguru` → stderr → the host's `server.log`) did not: sixteen lines
interpolated what he said or asked straight into a record, so a masked store sat next to an unmasked log. One door
instead of sixteen edits: a loguru patcher that runs the same `pii.tag` over every record's message while the switch is
on. It never raises and never recurses (the tagger logs its own failures), and a record it cannot read is withheld.
"""
from __future__ import annotations

import threading

_busy = threading.local()


def masked(message: str) -> str:
    """`message` as the log may carry it: tagged while `obfuscate` is on, untouched otherwise. Never raises."""
    if getattr(_busy, "on", False):          # the tagger's own debug line: never mask the masker
        return message
    _busy.on = True
    try:
        from config import privacy
        if not privacy.obfuscate():
            return message
        from observability import pii
        return pii.tag(message)
    except Exception:  # noqa: BLE001 — an unreadable switch or tagger: the line is withheld, not leaked
        return "[WITHHELD]"
    finally:
        _busy.on = False


def patch(record) -> None:
    """The loguru patcher (`logger.configure(patcher=patch)`): installed once at boot by `server/__main__`."""
    try:
        record["message"] = masked(record["message"])
    except Exception:  # noqa: BLE001
        pass

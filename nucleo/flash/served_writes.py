"""nucleo/flash/served_writes.py — which card WRITES landed, and when (2026-10-14; refactor2710-99).

Both channels pass every landed data-op through `circuit.compose.remember`, so that is where a WRITE (an action the
manifest does not declare as a view) is noted: a later op that made good an earlier refused one is read here
(`landed_since`). The sentence ring that answered the window lookback (V2-132) went with that lookback (A7: an errand
opens by the model's call or a sure verdict, never by a walk back over his words). Bounded, in-process.
"""
from __future__ import annotations

import time

_MAX = 32
#: Which (card, action) WRITE landed when — what a later op made good of an earlier refused one (refactor2710-99).
_landed: list[tuple[str, str, float]] = []


def _is_view(wid: str, action: str) -> bool:
    try:
        from widgets import runtime
        spec = ((runtime.get(str(wid or "").split("::", 1)[0]) or {}).get("actions") or {}).get(action)
        return bool(isinstance(spec, dict) and spec.get("view"))
    except Exception:  # noqa: BLE001 — unreadable manifest: not noted
        return True


def note(wid: str, action: str, text: str, res, *, now: float | None = None) -> None:
    """After a data-op: remember a WRITE that landed (`text` is the sentence it came from, kept in the signature)."""
    if not isinstance(res, dict) or res.get("ok") is False or res.get("error") or _is_view(wid, action):
        return
    _landed.append((str(wid or "").split("::", 1)[0].strip().lower(), str(action or ""), time.time() if now is None else now))
    del _landed[:-_MAX]


def landed_since(wid: str, action: str, since: float) -> bool:
    """Did a write of this card action LAND after `since`? (a retry that made good an earlier refusal)"""
    w = str(wid or "").split("::", 1)[0].strip().lower()
    return any(lw == w and la == action and at > since for lw, la, at in _landed)


def reset() -> None:
    _landed.clear()

"""nucleo/acts/correction_undo.py — a correction that does the last act on ANOTHER row undoes the first one.

Multi-turn bench (2026-11-12): «mueve la reunión con Marta de mañana a las diez a las doce» moved the 10:00; «no,
perdona, la otra, la de las cinco — la de las diez déjala como estaba» is ONE correction with two consequences: the
other row moves, and the first goes back. The model emitted the move of the other row only; the first stayed at 12:00.

The mechanism bounds a consequence, never a judgement: only when the brief reads `corrects_last` surely AND his turns'
last act was this card's (`stop.corrected_card`, a fact), the correcting act is the SAME action of that card, and the
card itself answers that its last act can be undone for an act on another row (`widgets.<card>.data.undo_of`, the
card's own hook — the card knows what its act wrote and where it was). Then the undo runs first, once per act, through
the same door. No word of his sentence is read here.
"""
from __future__ import annotations

import importlib

from loguru import logger

_UNDONE: set = set()
#: The undo each turn ran, by its trace: the model's OWN move back in the same turn («leave the 10 am one as it was»,
#: written as a second call) is that undo already — run again it would move the row that now sits in its place.
_RAN: dict = {}
UNDONE, ALREADY = "undone", "already"
#: This turn's calls on a card, by trace: a move back the model ALREADY wrote earlier in the turn is the undo itself.
_SEEN: dict = {}
#: Set while the undo itself runs through the door: its own call must not meet this hook again.
_IN_UNDO = __import__("contextvars").ContextVar("correction_undo_in_undo", default=False)


def _same(call: dict, undo: dict) -> bool:
    """Is this call the undo again — every key it carries, the undo carries with the same value?"""
    norm = lambda v: " ".join(str(v or "").split()).lower()  # noqa: E731
    keys = [k for k, v in (call or {}).items() if str(v or "").strip()]
    return bool(keys) and all(k in undo and norm(call[k]) == norm(undo[k]) for k in keys)


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def undo_first(wid: str, action: str, payload: dict | None, brief, *, apply, emit=None) -> str:
    """Run the card's undo of his last act before this correcting act, when every condition above holds: `UNDONE`.
    `ALREADY` when this call IS the undo this turn already ran (the caller drops it); "" otherwise. Never raises."""
    if _IN_UNDO.get():
        return ""
    try:
        from voice import trace as _trace
        tr = str(_trace.current() or "")
        ran = _RAN.get(tr)
        if ran and ran[0] == _base(wid) and ran[1] == str(action or "") and _same(dict(payload or {}), ran[2]):
            return ALREADY
        seen = _SEEN.setdefault(tr, [])
        if len(_SEEN) > 8:
            for k in list(_SEEN)[:-8]:
                _SEEN.pop(k, None)
        earlier = list(seen)
        seen.append((_base(wid), str(action or ""), dict(payload or {})))
        from nucleo import done_ops
        from nucleo.request import stop
        card = _base(wid)
        if not card or _base(stop.corrected_card(brief)) != card:
            return ""
        last = done_ops.his_last()
        if _base(last.get("wid")) != card or str(last.get("action") or "") != str(action or ""):
            return ""
        key = (str(last.get("trace") or ""), float(last.get("at") or 0.0))
        if key in _UNDONE or (key[0] and key[0] == str(_trace.current() or "")):
            return ""                        # undone already, or an act of THIS turn (his own two-act order)
        hook = getattr(importlib.import_module(f"widgets.{card}.data"), "undo_of", None)
        got = hook(action, dict(last.get("payload") or {}), dict(payload or {})) if callable(hook) else None
        if not got or any(c == card and a == got[0] and _same(p, got[1]) for c, a, p in earlier):
            return ""                        # no undo, or the model already wrote it earlier in this turn
        _UNDONE.add(key)
        _RAN.clear()
        _RAN[str(_trace.current() or "")] = (card, str(got[0]), dict(got[1]))
        if callable(emit):
            emit("brain", "↩️ a correction onto another row — the last act is undone first", text=f"{wid}:{got[0]}",
                 role="system", extra={"cat": "flash", "id": wid, "action": got[0], "payload": got[1]})
        tok = _IN_UNDO.set(True)
        try:
            apply(wid, got[0], got[1])
        finally:
            _IN_UNDO.reset(tok)
        return UNDONE
    except Exception as e:  # noqa: BLE001 — unread: the correcting act runs alone, as before
        logger.debug(f"correction_undo: not undone ({e!r})")
        return ""


def reset() -> None:
    _UNDONE.clear()
    _RAN.clear()
    _SEEN.clear()

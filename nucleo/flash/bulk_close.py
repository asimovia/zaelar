"""A close that names no card closes the OTHERS — never the card he is working on (V2-807 T-08).

THE DEFECT. «Close whatever you don't need right now» closed every card, including the draft he had corrected three
times in the previous minute. Two links: the model's plan («close the messages and the browser, keep the document»)
expressed the keep as a `show_widget` of the open document, which the close-turn guard discarded as «the order says
CLOSE»; and on the next fragment a bulk close with no id reached the canvas, whose client reads a bare close as
`closeAll()`.

THE CLASS. A bulk close — one that names no card — is a close of the cards he is NOT using. The card in use is never
in it unless his words name it. «In use» is read from facts, never from words:

  · the WORKING card — the newest card a data-op actually ran on (`done_ops`, the ledger every executed op crosses)
    within `WORKING_S`, and still open. One card at most: the object of the conversation, not everything touched.
  · a card the turn KEPT — a show of a card that is already open, during a close turn, is the model saying «keep
    this one» (`note_kept`); it is remembered for `KEPT_S`, long enough to cover the next fragment of the sentence.

With nothing in use the close is the bare one, exactly as before: `closeAll()` on the client. With an unknown canvas
(no report yet) it is also the bare one — inventing a keep from no data would be a new guess.

Every bulk-close door of a TURN goes through `close_all` (the verdict-driven fallback, the seeded action map, the
hard interrupt). The reset endpoints do not: a reset is the lifecycle, not an order about cards.
"""
from __future__ import annotations

import time

from loguru import logger

#: How long a data-op keeps its card «in use». A draft corrected a minute ago is still the object of the sentence; a
#: card touched ten minutes ago is not.
WORKING_S = 300.0
#: How long a model's «keep this one» lasts — the rest of the same sentence, which may arrive as the next fragment.
KEPT_S = 30.0

_KEPT: dict[str, float] = {}


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def note_kept(card: str) -> None:
    """The turn chose to KEEP `card` while closing others — a bulk close in the next `KEPT_S` spares it."""
    c = str(card or "").strip().lower()
    if c:
        _KEPT[c] = time.time()


def kept_now() -> list[str]:
    """The cards a recent turn chose to keep, still within `KEPT_S`."""
    now = time.time()
    for c in [c for c, at in _KEPT.items() if now - at > KEPT_S]:
        _KEPT.pop(c, None)
    return list(_KEPT)


def reset() -> None:
    """Forget every keep (tests, session reset)."""
    _KEPT.clear()


def _on_canvas(card: str, open_ids) -> str:
    """The open card `card` designates: itself when open, else the one open instance of its piece, else ""."""
    c = str(card or "").strip().lower()
    opened = [str(o or "").strip() for o in (open_ids or []) if str(o or "").strip()]
    if c in {o.lower() for o in opened}:
        return next(o for o in opened if o.lower() == c)
    same = [o for o in opened if _base(o) == _base(c)]
    return same[0] if len(same) == 1 else ""


def working_card(open_ids, *, within_s: float = WORKING_S) -> str:
    """The open card a data-op most recently RAN on, within `within_s` — "" when none is open."""
    try:
        from nucleo import done_ops as _done
        for row in reversed(_done.recent(within_s=within_s, limit=40)):
            hit = _on_canvas(str(row.get("wid") or ""), open_ids)
            if hit:
                return hit
    except Exception as e:  # noqa: BLE001
        logger.debug(f"bulk_close: working card unreadable — {e}")
    return ""


def in_use(open_ids, text: str = "") -> list[str]:
    """The open cards a bulk close must spare: the working card and the kept ones, minus any his words NAME."""
    spare: list[str] = []
    for c in [working_card(open_ids)] + kept_now():
        hit = _on_canvas(c, open_ids) if c else ""
        if hit and hit not in spare:
            spare.append(hit)
    if spare and text:
        try:
            from widgets import instances as _inst
            named = {_base(x) for x in _inst.named_in(text, spare)}
            spare = [c for c in spare if _base(c) not in named]
        except Exception as e:  # noqa: BLE001
            logger.debug(f"bulk_close: naming unreadable — {e}")
    return spare


def _open_instances() -> list[str]:
    try:
        from server.voice_api import open_instances
        return list(open_instances() or [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"bulk_close: canvas unreadable — {e}")
        return []


def close_all(emit, *, src: str, text: str = "", said: str = "", extra: dict | None = None,
              open_ids=None) -> list[str]:
    """Close every card he is not using. Returns the cards spared ([] = the bare close-all went out).

    `text` is his sentence (read to see whether it names a card in use); `said` is the phrase a caller already
    attaches to its canvas events (the action map does), passed through unchanged."""
    base = dict(extra or {})
    base["src"] = src
    kw = {"text": said} if said else {}
    opened = list(open_ids) if open_ids is not None else _open_instances()
    spare = in_use(opened, text) if opened else []
    if not spare:
        emit("widget", "close", extra=base, **kw)
        return []
    for cid in opened:
        if cid not in spare:
            emit("widget", "close", extra={**base, "id": cid}, **kw)
    emit("brain", "🧷 bulk close: the card in use stays", text=",".join(spare), role="system",
         extra={"cat": "flash", "kept": spare, "src": src})
    return spare

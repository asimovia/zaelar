"""voice/canvas_src.py — WHO changed the canvas, as the canvas itself reports it (V2-807 T-15).

The browser is authoritative for what is on screen, and `POST /api/canvas/state` turns every difference
between two reports into a `widget show|close` event. Those events used to be stamped `src: "user"` — all of
them — so a card the client opened from its own code (a restore, the echo of an engine command, a fast path)
read on the timeline, and in the arbiter, as the operator's own hand.

The report now carries a CAUSE per changed card (`by`), named by the host at the call site that changed it:

  · `hand`            — a pointer or key gesture of the operator (a close button, a catalogue tile, a chip).
  · anything else     — code in the client: `engine` (the echo of an engine command), `restore`, `reset`,
                        `card` (the card's own code closed itself), `screens`, `console`, `url`, `code`…

Only `hand` keeps the `user` provenance. Everything else is `client:<cause>`, and a report that names no cause
is `client` — an unknown origin is never promoted to the operator's hand.

Both forms are still the canvas's OWN report: no screen obeys them (`is_report`), exactly as `user` alone was
before. That rule lives here once so every reader asks the same question.
"""
from __future__ import annotations

#: The provenance of a change the operator made with his own hands. Unchanged since V2-039.
HAND = "user"
#: The provenance family of every other change the canvas reports.
CLIENT = "client"

#: The causes the two hosts name (`frontend/app/widgets/desktop.js`, `frontend/mobile/app/shell/Deck.js`).
BY_HAND = "hand"
BY_ENGINE = "engine"        # the echo of an engine command — judged when the engine issued it
RESTORE = "restore"         # the page coming back with the cards it had
RESET = "reset"             # a session reset emptying the canvas
SCREENS = "screens"         # another screen took a one-screen card
CARD = "card"               # a card closing itself (a timer that ends, a sheet that fades)
#: Changes that are the canvas's own lifecycle, not a decision anybody has to license.
LIFECYCLE = (RESTORE, RESET, SCREENS, CARD)


def _clean(cause) -> str:
    s = str(cause or "").strip().lower()
    return "".join(ch for ch in s if ch.isascii() and (ch.isalnum() or ch == "-"))[:24]


def cause_of(src) -> str:
    """The client cause inside a `client:<cause>` src ("" for anything else)."""
    s = str(src or "")
    return s.split(":", 1)[1] if s.startswith(CLIENT + ":") else ""


def of(cause) -> str:
    """The `src` for one canvas change, from the cause the client named for it."""
    c = _clean(cause)
    if c == BY_HAND:
        return HAND
    return f"{CLIENT}:{c}" if c else CLIENT


def causes(raw) -> dict:
    """The report's `by` map, keyed by BASE widget id (the diff is computed on base ids)."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, v in list(raw.items())[:60]:
        base = str(k or "").split("::", 1)[0].strip().lower()
        if base:
            out[base] = v
    return out


def is_report(src) -> bool:
    """Is this `src` the canvas reporting what already happened on a screen (never an order to obey)?"""
    s = str(src or "")
    return s == HAND or s == CLIENT or s.startswith(CLIENT + ":")

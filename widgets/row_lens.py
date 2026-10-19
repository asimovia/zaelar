"""widgets/row_lens.py — a lens over a row HIS words name goes where the ROW is, never where a sentence put it.

Demo pass 140 (2026-10-19), R2: «and when does anna's vacation start? show me in the calendar». The model answered
from memory and stumbled — «it starts tomorrow, 20 December… sorry, 20 October» — and called only `show_widget`.
The promise repair then asked for the call and was handed that reply: it chose `agenda:show_day {day: 2026-10-20}`,
the card came up on a day with no vacation in it, and the read of that day «corrected» the reply into «her vacation
hasn't started yet». The row was on file the whole time: «Anna vacation», 2026-12-20, which `open_meeting` opens on
its own day and answers with. One wrong word in a sentence decided which data the turn looked at.

The class: a lens that moves the card to WHERE something is (a day) is run on a turn whose operator words name
exactly one row the card holds. Then the row decides, through the card's own item view, and the place comes off the
data. The card DECLARES it on the lens — `"by_row": "<its item view>"` (agenda: `show_day` → `open_meeting`) — because
whether a lens points at a row's place is the card's knowledge: `imagenes:show` or `map:add` take a subject that may
share words with a row on screen and must stay a new search. Read from the manifest and `widgets.refs`; nothing here
knows a word or a card. Untouched: a sentence that names no row («show me tomorrow»), several (refs asks), or a lens
that declares nothing.
"""
from __future__ import annotations


def _actions(widget_id: str) -> dict:
    try:
        from widgets import runtime
        return dict((runtime.get(widget_id) or {}).get("actions") or {})
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.warning(f"row_lens: no manifest for {widget_id} ({type(e).__name__})")
        return {}


def retarget(widget_id: str, action: str, payload: dict, order: str) -> tuple[str, dict]:
    """(action, payload) to run: the declared item view on the one row his words name, or what came in. Never raises."""
    try:
        from widgets import refs as _refs
        base = str(widget_id or "").split("::", 1)[0].strip().lower()
        acts = _actions(base)
        view = str((acts.get(str(action or "").strip()) or {}).get("by_row") or "")
        field = _refs.id_field_for_action(base, view) if view in acts else None
        words = str(order or "").strip()
        if not (field and words):
            return action, payload
        got = _refs.resolve(base, view, "", {}, order=words)
        row = str((got.payload or {}).get(field) or "") if got.ok else ""
        if not row:
            return action, payload
        from loguru import logger
        logger.info(f"row_lens: {base}:{action} {payload} → {view} {{{field}: {row!r}}} (his words name the row)")
        return view, {field: row}
    except Exception as e:  # noqa: BLE001 — the lens runs as the model sent it
        from loguru import logger
        logger.warning(f"row_lens: {widget_id}:{action} kept as sent ({type(e).__name__}: {e})")
        return action, payload

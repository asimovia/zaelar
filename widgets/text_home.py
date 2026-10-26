"""widgets/text_home.py — a message to someone has ONE home: its held row on the card that sends it (V2-807 T-09).

Measured (2026-10-26): a held email lived as a row of the mail card, and a COPY of it was put in a document sheet.
Every spoken correction rewrote the copy (three whole new bodies, each «✅ done» against the document's own field);
«send it» sent the row, i.e. the original text. One outbound message had two bodies, and the one that leaves was the
one nobody corrected.

The rule is two declarations and one door, with no reading of what the words mean:
  · an action that writes free text on a card names the payload field that carries it (`"text_field": "body"` on
    `documento:show`);
  · a card that holds outbound messages for his word says so (`"claims_text": true`) and answers
    `claim_text(text, title) -> {action, payload} | None` in its data module: is this text a version of a message
    I hold? (`widgets/mensajeria/held.claim` measures overlap with the held draft, and its recipient address).

`route` asks every claimer; a claim turns the write into the claimer's own action on that row. Two callers use it:
the turn's data door (`redirect`, which also brings the claimer's card through the one canvas door) and the widget
funnel (`server_api._dispatch`, for every other caller). Never raises: an unreadable claim leaves the write as it was.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("zaelar.widgets.text_home")

#: The manifest key of an action's free-text field, and of a card that holds outbound messages.
TEXT_FIELD = "text_field"
CLAIMS = "claims_text"


def route(wid: str, action: str, payload: dict | None) -> dict | None:
    """`{widget, action, payload, from, to, why}` when the text this write carries belongs on another card's row."""
    try:
        from . import runtime
        base = str(wid or "").split("::", 1)[0].strip().lower()
        act = str(action or "").strip()
        spec = ((runtime.get(base) or {}).get("actions") or {}).get(act)
        field = spec.get(TEXT_FIELD) if isinstance(spec, dict) else None
        p = payload if isinstance(payload, dict) else {}
        text = str(p.get(field) or "") if field else ""
        if not text.strip():
            return None
        for m in runtime.catalog() or []:
            other = str(m.get("id") or "")
            if not m.get(CLAIMS) or not other or other == base:
                continue
            hook = getattr(importlib.import_module(f"widgets.{other}.data"), "claim_text", None)
            got = hook(text, str(p.get("title") or "")) if callable(hook) else None
            if isinstance(got, dict) and got.get("action") and isinstance(got.get("payload"), dict):
                return {"widget": other, "action": str(got["action"]), "payload": dict(got["payload"]),
                        "from": f"{base}:{act}", "to": str(got.get("to") or ""), "why": str(got.get("why") or "")}
    except Exception as e:  # noqa: BLE001 — the write goes where it was sent
        logger.info(f"text_home: route unreadable ({type(e).__name__}: {e})")
    return None


def record(home: dict, emit=None) -> None:
    """The redirect on the timeline: what was written where, and why it went to the row instead."""
    try:
        if emit is None:
            from voice.observer import emit
        emit("widget", "✉️ a held message's text goes to its row, not to a copy",
             text=f"{home['from']} → {home['widget']}:{home['action']} ({home.get('to') or '?'})",
             extra={"from": home["from"], "id": home["widget"], "action": home["action"],
                    "to": home.get("to") or "", "why": home.get("why") or "",
                    "key": str((home.get("payload") or {}).get("key") or "")})
    except Exception as e:  # noqa: BLE001
        logger.info(f"text_home: record failed ({e})")


def redirect(wid: str, action: str, payload: dict | None, *, emit=None, present=None) -> tuple[str, str, dict]:
    """The turn's door: `(wid, action, payload)` to run — the claimer's own action when the text is its message,
    and its card brought through `present` (the one canvas door) so the draft is where he looks."""
    home = route(wid, action, payload)
    if home is None:
        return wid, action, payload if isinstance(payload, dict) else {}
    record(home, emit)
    if present is not None:
        try:
            present(home["widget"], reason="turn-order", action=home["action"], src="flash", emit=emit)
        except Exception as e:  # noqa: BLE001
            logger.info(f"text_home: present failed ({e})")
    return home["widget"], home["action"], home["payload"]

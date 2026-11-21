"""tests/widget_data_rig.py — one `widget_data` call through the REAL data-op gate, and what it ended in.

A test hands the card, the action, the payload, his words and the turn's brief; this runs
`tool_executor_widget_calls._apply_widget_data` with every gate it has (held row, two readers on an act that leaves,
the ordered send, the stranger's-text gate) and stops at the two places an act leaves the gate:

  · `ran`    — the ops that STARTED (`data_ops.start_op`), as `(card, action, payload)`; nothing is dispatched;
  · `asked`  — the ops held for his yes (`_request_data_confirm`), same shape;
  · `events` — every `(kind, label)` the gate emitted.

The brief is a plain dict, or `brief(...)` builds one the way `turn_brief.read` reads it. Shared by the message door
(refactor2710-06) and the card door (refactor2710-05).
"""
from __future__ import annotations



def brief(screen_action: str = "", confidence: float = 0.95, *, kind: str = "order", open_ids=("mensajeria",)) -> dict:
    """A settled turn brief whose `screen_action` reads `card:action` at `confidence` and whose request is `kind`."""
    import threading
    ev = threading.Event()
    ev.set()
    result = {"request_type": {"choice": kind, "confidence": 1.0}}
    if screen_action:
        result["screen_action"] = {"choice": screen_action, "confidence": confidence}
    return {"event": ev, "turn_id": "t-rig", "open_ids": list(open_ids), "result": result}


def scene(tmp_path, monkeypatch):
    """The messaging scene the send tests share: an isolated store, Quinn in the directory, the mail card open, and no
    stranger's words nor his recent ones carried in from another test (both are process state)."""
    from nucleo import his_words, untrusted
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    import server.voice_api as _va
    monkeypatch.setattr(_va, "open_instances", lambda: ["mensajeria"])
    untrusted.reset()
    his_words.reset()

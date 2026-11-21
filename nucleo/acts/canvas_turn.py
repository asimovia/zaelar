"""The `arbiter` record of canvas acts that did not cross the door, judged by their provenance as the door judges
(refactor2710-04; INI-078 L1). `shadow_tap` sees every recorded `widget` event and writes, unenforced, the verdict
the door would give; `judged()` keeps the door's own emits from being judged twice."""
from __future__ import annotations

import contextlib

from nucleo.acts import canvas_arbiter as _tree
from nucleo.acts.arbiter_event import emit_verdict as _emit_verdict  # noqa: F401 — the door and the tap write it

_in_tap = False                     # re-entrancy guard: our own verdict emit must not re-enter the tap


@contextlib.contextmanager
def judged():
    """While the door emits what it already judged, the tap must not judge it a second time."""
    global _in_tap
    prev, _in_tap = _in_tap, True
    try:
        yield
    finally:
        _in_tap = prev


def shadow_tap(kind: str, label: str, text: str, role: str, extra: dict | None) -> None:
    """Called by `voice/observer.emit` for every recorded event: judges, as shadow, a canvas act that did not cross
    the door. Never raises, never mutates the event it observes."""
    global _in_tap
    if _in_tap or kind != "widget":
        return
    try:
        _in_tap = True
        ex = extra or {}
        op, action = "", ""
        if label == "show":
            op, action = "show", str(ex.get("action") or "")
        elif label == "close":
            op = "close"
        elif isinstance(label, str) and label.startswith("data:"):
            op, action = "data", label.split(":", 1)[1]
        elif label == "action":
            op, action = "data", str(ex.get("action") or "")
        if not op:
            return
        wid = str(ex.get("id") or "").strip().lower()
        src = str(ex.get("src") or "") or _prov_src(wid)
        if src == "client:engine":      # `voice.canvas_src.of(BY_ENGINE)`: judged when the engine issued it
            return
        _emit_verdict(op, wid, src, action, _tree.decide(op, wid, src, action=action), shadow=True)
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"canvas_turn: shadow verdict not written ({e!r})")
    finally:
        _in_tap = False


def _prov_src(wid: str) -> str:
    try:
        from widgets import provenance
        return provenance.who(wid)
    except Exception:  # noqa: BLE001
        return "system"

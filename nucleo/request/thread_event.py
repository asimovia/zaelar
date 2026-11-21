"""nucleo/request/thread_event.py — ONE event per thread decision (V2-878 §6).

Which errand a request belongs to is decided at the switchboard (V2-931); the decisions that still happen around an
errand are emitted here, each as one event of kind `thread` (family `worker`, beside `flow`), written here and nowhere
else:

  · `decided`      — his words handed back by a worker (`evicted`) or kept on a card as a deferred choice
                     (`pick_pending`): `verb`, `as`, `id`, `by`, `menu`, `heard` (his words, cut) and
                     `window_had_commission`.
  · `judged`       — the model judge's menu and its answer, with who asked (`caller`) and how long it took.
  · `recall`       — the recall / recent-conversation shortcuts fired, and in which language.
  · `would_relay` / `arbiter` — the shadow measurements of V2-878 §5.

Emit-only and fail-open: a decision that cannot be emitted never changes how a turn goes.
"""
from __future__ import annotations

from loguru import logger

KIND = "thread"
#: The verbs a decision emitted here carries.
EVICT, PICK_PENDING = "evict", "pick_pending"
HEARD_MAX = 80


#: The decisions each trace (turn) carried, newest traces last and bounded — read after the turn by the whisperer's
#: gate (`nucleo/whisper/gate.py`), which only weighs what the turn already decided and never asks again.
_BY_TRACE: dict[str, list[str]] = {}
_TRACE_MAX = 64


def of_trace(tid: str) -> list[str]:
    """The `event` or `event:verb` names this trace's thread decisions emitted, in order ([] for an unknown trace)."""
    return list(_BY_TRACE.get(str(tid or ""), ()))


def reset() -> None:
    _BY_TRACE.clear()


def _note_trace(name: str) -> None:
    from voice import trace as _trace
    tid = _trace.current()
    if tid:
        _BY_TRACE.setdefault(tid, []).append(name)
        while len(_BY_TRACE) > _TRACE_MAX:
            _BY_TRACE.pop(next(iter(_BY_TRACE)))


def _send(event: str, label: str, text: str, extra: dict) -> dict | None:
    try:
        _note_trace(f"{event}:{extra['verb']}" if extra.get("verb") else event)
        from voice import observer
        payload = {"cat": "worker", "event": event, **extra}
        observer.emit(KIND, label, text=str(text or "")[:200], role="system", extra=payload)
        return payload
    except Exception as e:  # noqa: BLE001 — evidence that cannot be emitted never changes how a turn goes
        logger.debug(f"thread_event: {event} not emitted — {type(e).__name__}: {e}")
        return None


def evicted(words: str, flow: str) -> dict | None:
    """A worker handed his words back: they leave that errand and never fold into it again."""
    extra = {"verb": EVICT, "as": "", "id": str(flow or ""), "by": "handed_back", "menu": [str(flow or "")],
             "heard": str(words or "")[:HEARD_MAX], "window_had_commission": True}
    return _send("decided", f"🧵 thread: evict ← {flow}", extra["heard"], extra)


def judged(request: str, menu: list[tuple[str, str]], answer: str, *, ms: float, outcome: str) -> dict | None:
    """The model judge's menu and answer. `outcome`: about · separate · unreadable · error."""
    extra = {"caller": "dispatch", "menu": [{"id": str(t), "goal": str(g or "")[:HEARD_MAX]} for t, g in menu[:12]],
             "answer": str(answer or ""), "outcome": str(outcome or ""), "ms": round(float(ms or 0.0), 1),
             "heard": str(request or "")[:HEARD_MAX]}
    return _send("judged", f"⚖️ thread judge: {outcome}" + (f" → {answer}" if answer else ""), extra["heard"], extra)


# ── V2-878 §5, in SHADOW: the deferred choice and the screen↔errand arbiter (`nucleo/turn/pick_pending.py`) ─────────

def pick_pending(note: dict, *, shadow: bool = True) -> dict | None:
    """A request routed into an errand with no rows yet, kept on its card as a choice to make when the rows arrive."""
    extra = {"verb": PICK_PENDING, "as": "", "id": str(note.get("flow") or ""), "by": "verdict", "shadow": shadow,
             "menu": [str(note.get("flow") or "")], "heard": str(note.get("heard") or "")[:HEARD_MAX],
             "window_had_commission": True}
    return _send("decided", f"🧵 thread: pick_pending → {extra['id']}", extra["heard"], extra)


def would_relay(uid: str, sheet: str, pick: dict) -> dict | None:
    """The first rows landed on an errand that holds a deferred choice: what WOULD be relayed to its worker."""
    extra = {"uid": str(uid), "sheet": str(sheet), "heard": str(pick.get("heard") or "")[:HEARD_MAX],
             "held_s": max(0, int(__import__("time").time()) - int(pick.get("at") or 0)), "shadow": True}
    return _send("would_relay", "🧵 thread: first rows — would relay his deferred choice", extra["heard"], extra)


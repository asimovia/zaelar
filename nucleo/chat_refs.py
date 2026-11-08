"""nucleo/chat_refs.py — every errand that delivers into a card leaves a REFERENCE on the chat wall (V2-862).

Operator, 2026-11-08: a long report went into the `documento` card instead of the chat, which is right — but once
he closed the card, nothing in the conversation said it had ever existed. «a little box in the chat with a reference
to the document, so that even if the user closes it he can go back through the thread and get it back easily».
And then: «it must be mechanical and deterministic, for every creation of documents, code, images — any content we
build in a worker. Even if it is left half done, the reference stays in the chat».

THE MECHANISM, and why each piece sits where it does:

  · BORN at the dispatcher's single door (`dispatch/listener.py`), right after the surface is sealed. Every errand,
    from every door (his turn, auto-resume, the confirm gate, a relay) passes there, and the surface is the one
    declared fact that says whether the errand delivers into a card (`surfaces.delivers_no_card`). No reading of
    his words, no model, no table of content types: the surface decides.
  · CLOSED where the errand's sheets are already closed (`dispatch/session_steps.py` and the unrun path in
    `dispatch/session.py`), with the ending the record carries. An errand that parks on a question is not closed:
    its reference keeps saying it is in progress, which is the truth.
  · ONE event kind, `artifact`, through `voice.observer.emit` — so the same event is the observability record (the
    `worker` family, correlated by the errand's trace) AND what the chat wall receives over SSE. The wall upserts by
    `ref` (the task's row id), so a relay, a resume or a retitle updates the same box instead of adding another.
  · EVERY errand gets exactly one decision on record: `opened` (a box is drawn) or `skipped` with its reason
    (`no_card` · `child` · `event` · `cluster` · `no_row`). «Did the reference get made, and if not why?» is one
    query of the `artifact` kind, never an inference from silence.
  · REOPENING is not this module's: the box calls the existing door (`POST /api/tasks/reopen` →
    `nucleo/turn/task_recall.reopen`), which rebuilds the deliverable from what the task kept.

What is NOT his: an errand started by another errand (`depth`/`parent_task_id` — its parent already has a box), an
errand born from an arriving event with no turn of his behind it (`origin == "event"`, the stream worker), and work a
cluster peer asked for (`src == "cluster"`). The chat wall is the operator ↔ zaelar conversation.

Fail-soft everywhere: a reference that could not be drawn must never touch the errand it refers to.
"""
from __future__ import annotations

import threading

from loguru import logger

KIND = "artifact"

#: The last card each errand SHOWED, keyed by its session key (`worker:<key>` is the canvas `src`). A `widget` errand
#: builds or fills a card of his that no surface names in advance; this is how its box learns which card to reopen.
_SHOWN: dict[str, str] = {}
_MX = threading.Lock()
_CAP = 256


def _key_of(rec) -> str:
    return str(getattr(rec, "task_id", "") or "")


def _title_of(rec) -> str:
    return str(getattr(rec, "title", "") or getattr(rec, "goal", "") or "").strip()[:160]


def not_his(rec, ctx: dict | None) -> str:
    """Why this errand's reference does NOT belong on his chat wall, or "" when it does. Pure."""
    c = ctx or {}
    from nucleo import surfaces as _surf
    if _surf.delivers_no_card(getattr(rec, "surface", "")) or not getattr(rec, "surface", ""):
        return "no_card"
    if int(getattr(rec, "depth", 0) or 0) > 0 or str(getattr(rec, "parent_task_id", "") or ""):
        return "child"
    if str(c.get("origin") or "") == "event":
        return "event"
    if str(c.get("src") or "") == "cluster":
        return "cluster"
    if not str(getattr(rec, "uid", "") or ""):
        return "no_row"          # the reopen door is keyed by the row: a box with no row could open nothing
    return ""


def card_of(rec) -> str:
    """The card instance this errand's deliverable lives in, or "" when it is not known yet."""
    from nucleo import surfaces as _surf
    surface = str(getattr(rec, "surface", "") or "")
    base = _surf.deliverable_card(surface)
    if base == "results":
        try:
            from nucleo import dispatch as _d
            from widgets.results import data as _sheet
            sid = _d.sheet_of(rec)
            return _sheet.instance_id(sid) if sid else "results"
        except Exception:  # noqa: BLE001
            return "results"
    if base:
        return base
    with _MX:
        return _SHOWN.get(_key_of(rec), "")


def _fields(rec, **more) -> dict:
    return {"ref": str(getattr(rec, "uid", "") or ""), "task_id": _key_of(rec),
            "surface": str(getattr(rec, "surface", "") or ""), "card": card_of(rec), "title": _title_of(rec),
            **more}


def _emit(label: str, rec, fields: dict) -> None:
    try:
        from voice import trace as _trace
        from voice.observer import emit
        with _trace.scope(str(getattr(rec, "trace_id", "") or "")):
            emit(KIND, label, text=str(fields.get("title") or ""), role="system", extra=fields)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"chat_refs: {label} not emitted: {e!r}")


def opened(rec, ctx: dict | None = None) -> bool:
    """The errand was commissioned: draw its box (`opened`) or record why not (`skipped`). True when drawn."""
    try:
        why = not_his(rec, ctx)
        if why:
            _emit("skipped", rec, _fields(rec, state="", reason=why))
            return False
        rec.chat_ref = True
        _emit("opened", rec, _fields(rec, state="started"))
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"chat_refs: opened failed: {e!r}")
        return False


def retitled(rec) -> None:
    """The errand got its composed name: the box says it too."""
    if getattr(rec, "chat_ref", False):
        _emit("retitled", rec, _fields(rec, state="started"))


def state_of(rec) -> str:
    """How the errand ended, in the box's three words: `done` · `partial` (it ended without its deliverable being
    finished — failed, cut or stopped; what it wrote so far is kept) · `cancelled` (stopped by him)."""
    status = str(getattr(rec, "status", "") or "")
    if status == "done" and bool(getattr(rec, "ok", True)):
        return "done"
    if status == "cancelled":
        return "cancelled"
    return "partial"


def closed(rec, *, file: str = "") -> None:
    """The errand ENDED (any way): the box says how, and which card and file now hold what it made."""
    try:
        if not getattr(rec, "chat_ref", False):
            return
        fields = _fields(rec, state=state_of(rec), file=str(file or ""))
        _keep_card(rec, fields.get("card") or "")
        _emit("closed", rec, fields)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"chat_refs: closed failed: {e!r}")
    finally:
        with _MX:
            _SHOWN.pop(_key_of(rec), None)


def _keep_card(rec, card: str) -> None:
    """Record on the task which card held its deliverable, so the reopen door can answer for a surface that keeps
    no copy of its own (a `widget` errand, the picture viewer). The `results` and `documento` surfaces keep theirs."""
    uid = str(getattr(rec, "uid", "") or "")
    if not uid or not card:
        return
    try:
        from nucleo.circuit import ledger as _tasks
        _tasks.store().artifact_put(uid, "card", {"instance": card, "surface": str(getattr(rec, "surface", "") or "")})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"chat_refs: card not kept: {e!r}")


def note_show(src: str, wid: str) -> None:
    """The canvas door showed `wid` for `src`: when that is an errand (`worker:<key>`), remember it. Never raises."""
    try:
        s = str(src or "")
        if not s.startswith("worker:") or not wid:
            return
        with _MX:
            _SHOWN[s.split(":", 1)[1]] = str(wid)
            while len(_SHOWN) > _CAP:
                _SHOWN.pop(next(iter(_SHOWN)))
    except Exception:  # noqa: BLE001
        pass

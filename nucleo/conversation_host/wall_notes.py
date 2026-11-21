"""The engine's lines on the chat wall beside the manager's (INI-078, the wall of one writer): every line of the wall
has ONE writer, and these are the engine's — written as actions with ids through the wall's one door (`wall._say`),
each by its writer, with the role, kind, state and data the screen draws them by:

  · `notice`  a notice's 🔔 line, where the notice paints itself apart from the mouth (no voice of the manager holds
              it, or an owed one drained to a screen): id `notice_<key>`, one per notice. The question of a card open
              now is not drawn again (its card is its one place on screen), nor what the last line already says;
  · `record`  the one line an answered confirmation question leaves, a note in the system's colour;
  · `ref`     an errand's reference box, one per task row (`ref_<row>`), replaced in place by every later event of it
              with the card and file it already had; the replace carries the box's role, so a screen that has not
              got it yet appends it (`frontend/app/services/wall-bridge.js`). A skipped errand draws none.
"""
from __future__ import annotations

import threading
import time

from nucleo.conversation_host import wall

MARKERS = ("🔔", "💬")                      # the marks a line of ours may lead with: not its words
KEPT = 512

_lock = threading.Lock()
_refs: dict[str, dict] = {}                 # a reference box → its data so far (each event merges into it)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _line_id(prefix: str) -> str:
    """A line with no identity of its own: the prefix, the instant and the process's sequence, base 36."""
    from nucleo import runtime_ids

    def b36(n: int) -> str:
        out = ""
        while True:
            n, r = divmod(n, 36)
            out = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + out
            if not n:
                return out
    return f"{prefix}_{b36(_now_ms())}{b36(runtime_ids.next_seq('wall_line'))}"


def _bare(text) -> str:
    """A line's words without the mark it leads with."""
    t = str(text or "").strip()
    for m in MARKERS:
        if t.startswith(m):
            return t[len(m):].strip()
    return t


def _flat(text) -> str:
    """A question as two screens compare it: no mark, no emphasis, one space, lower case."""
    return " ".join(_bare(text).translate(str.maketrans("", "", "`*_")).split()).lower()


def _open_question(text) -> bool:
    """Is `text` the question of a card open now? Its card is that question's one place on screen: the same words
    notified are not drawn again as a line. A card is a row waiting on his answer that asks his consent."""
    t = _flat(text)
    if not t:
        return False
    try:
        from nucleo.circuit import asker, ledger
        rows = ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=20)
        for r in rows:
            if str(r.get("waiting_for") or "") != ledger.USER_ANSWER or not r.get("ask_id"):
                continue
            if asker.kind_of(asker.artefact(str(r.get("id") or ""))) == asker.KIND_CLARIFY:
                continue                    # a clarification is dialogue, said in the chat — no card
            ask = r.get("ask")
            if _flat(ask.get("text") if isinstance(ask, dict) else ask) == t:
                return True
    except Exception as e:  # noqa: BLE001 — unread: the line is drawn, as when no card is open
        from loguru import logger
        logger.debug(f"wall_notes: the open cards' questions were not read ({e!r}); the line is drawn")
    return False


def notice(text: str, key: str = "") -> None:
    """A notice painted apart from the mouth: its 🔔 line, by its key (one per notice: the same key again is the same
    line). Not when it is the question of an open card, nor when the last line already says it."""
    text = str(text or "")
    if not text.strip() or _open_question(text):
        return
    last = wall.last_line()
    if last and last[0] == "agent":
        a, b = _bare(last[1]), _bare(text)
        if a and b and a.startswith(b):
            return
    lid = f"notice_{key}" if key else _line_id("a")
    wall._say("notice", {"op": "append", "id": lid, "role": "agent", "state": "final", "text": "🔔 " + text,
                         "data": {"trace": ""}, "at": _now_ms()})


def record(text: str) -> None:
    """The one record line an answered question leaves: a note of its own colour."""
    text = str(text or "")
    if not text:
        return
    wall._say("record", {"op": "append", "id": _line_id("n"), "role": "note", "kind": "record",
                         "data": {"role": "record", "text": text}, "text": text, "at": _now_ms()})


def ref(fields: dict, label: str = "") -> None:
    """An errand's reference box: drawn at its first event, replaced in place by every later one (its card and file
    kept when a later event does not name them). A skipped errand draws none."""
    f = fields or {}
    key = str(f.get("ref") or "")
    if not key or label == "skipped":
        return
    row = {"role": "ref", "ref": key, "text": str(f.get("title") or f.get("text") or ""),
           "surface": str(f.get("surface") or ""), "card": str(f.get("card") or ""),
           "state": str(f.get("state") or "started"), "file": str(f.get("file") or "")}
    lid = f"ref_{key}"
    with _lock:
        was = _refs.get(lid)
        data = row if was is None else {**was, **row, "text": row["text"] or was.get("text", ""),
                                        "card": row["card"] or was.get("card", ""),
                                        "file": row["file"] or was.get("file", "")}
        _refs[lid] = data
        while len(_refs) > KEPT:
            _refs.pop(next(iter(_refs)))
    wall._say("ref", {"op": "append" if was is None else "replace", "id": lid, "role": "box", "kind": "ref",
                      "data": data, "text": data["text"], "at": _now_ms()})


def _reset_for_tests() -> None:
    with _lock:
        _refs.clear()

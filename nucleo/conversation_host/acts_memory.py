"""The `Tools` port's acts on his MEMORY (R-4, E7d-4): the model forgets or corrects a pill BY ITS ID, after reading
it with `recall` (which gives each pill with its id) — nothing here matches his words against the memory.

  forget   the pills, soft and undoable (`memory.api.forget_ids`): gone from recall, kept for audit; a pinned one stays
  correct  the pill's new text through the memory's one writer (`memory.api.write`, with `supersedes`): the same kind,
           level and slot, the old one superseded — never edited in place
"""
from __future__ import annotations

from conversation.ports import ToolResult


def _forget(args: dict) -> ToolResult:
    from memory import api as memory
    ids = args.get("ids") if isinstance(args.get("ids"), list) else [args.get("ids")] if args.get("ids") else []
    gone = memory.forget_ids(ids)
    if not gone:
        return ToolResult("failed", {"reason": "no such pill to forget (read it with recall: its id)", "ids": ids})
    return ToolResult("ok", {"forgotten": gone, "undo": "forgotten softly: it can be brought back"})


def _correct(args: dict) -> ToolResult:
    from memory import api as memory
    old, text = memory.pill(args.get("id")), str(args.get("text") or "").strip()
    if old is None or not text:
        return ToolResult("failed", {"reason": "no such pill, or no new text (read it with recall: its id)"})
    import json
    meta = json.loads(old.get("meta") or "{}") if isinstance(old.get("meta"), str) else dict(old.get("meta") or {})
    memory.write(text, level=str(old["level"]), kind=str(old["kind"]), slot=old.get("slot") or None,
                 pinned=bool(old.get("pinned")), meta={**meta, "corrects": int(old["id"])}, supersedes=[int(old["id"])])
    return ToolResult("ok", {"corrected": int(old["id"]), "now": text})


DOORS = {f.__name__.lstrip("_"): f for f in (_forget, _correct)}   # each door by its op


def run(op: str, args: dict) -> ToolResult:
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    return door(args if isinstance(args, dict) else {})

"""The draft's acts BY NUMBER (INI-078 segregation S4): the model, the one decider, acts on the open message by its
`#n` in OPEN — `draft_edit(#n, to?, text?, channel?, at?)`, `draft_send(#n)`, `draft_drop(#n)` — and nothing reads his
sentence about it before the model any more.

The owner still decides everything that is its own (`owner._step`): who a name is (`send/people`; several is a
question naming them), what is missing, and whether a go-ahead counts — only a confirmation he HEARD is answered, and
never one another line of ours came after (`send/heard.answers`). The model only brings the fields. A number that is
not the open draft fails and gives OPEN back: never a guess.
"""
from __future__ import annotations

from nucleo.send import draft as _draft
from nucleo.send import row as _row

#: the read each act stands for (the owner's own read shape, `send/read.NOTHING`)
OPS = ("edit", "go", "drop")


def _got(op: str, args: dict) -> dict:
    from nucleo.send import read
    got = {**read.NOTHING, "mine": True}
    if op == "go":
        got["send"] = True
    elif op == "drop":
        got["drop"] = True
    else:
        text = args.get("text")
        got.update(who=str(args.get("to") or "").strip(),
                   text=" ".join(str(text).split()) if isinstance(text, str) and text.strip() else None,
                   channel=str(args.get("channel") or "").strip().lower(), at=str(args.get("at") or "").strip())
        if got["channel"] not in ("whatsapp", "telegram", "email"):
            got["channel"] = ""
    return got


def the_draft(which) -> "_draft.Draft | None":
    """The open draft the `#n` names (its number, or its row id); None when that is not the draft open now."""
    d = _draft.current()
    w = str(which or "").strip().lstrip("#")
    if d is None or not w or not getattr(d, "row", ""):
        return None
    row = _row._get(d.row)
    return d if w in (str(row.get("num") or ""), d.row) else None


async def act(op: str, which, args: dict, said: str, last_line: str) -> tuple[bool, str]:
    """`(found, line)`: the act applied to the draft `which` names, under its lock (one at a time, as his sentences
    were). Not found → (False, "")."""
    from nucleo.send import owner
    d = the_draft(which)
    if d is None or op not in OPS:
        return False, ""
    got = _got(op, args)
    async with d.lock:
        if _draft.current() is not d:
            return False, ""
        _draft.touch(d)
        _row.resumed(d)
        line = await owner._step(d, got, last_line, said)
        owner._emit("acted by number", d, op=op, said=str(said)[:200], read=got, line=line[:200])
    _row.asked(line, d)
    if _draft.current() is None:
        _row._open_next_soon()
    return True, line

"""Which rows asked him since our last reply — by `ask_id`, never by the words we said (CRIT-K2b R6, V2-893 L4).

The one asker notes every question it puts to him (`asker.ask`), wherever it is said — the turn's mouth or out of
turn; the «which task?» doubt notes the rows it names (`among`). His turn reads them when its window is built
(`prior_line.snapshot` → `turn_began`), and the identity only ADVANCES when a reply of ours closed a turn since the
last read (a new assistant line in the window): a fragment of his that was dropped («the sentence went on»), a barge-in
before the bind, a resumed sentence — none spends it. What a turn may answer by identity is the row that asked ALONE
among the rows still waiting, or a row our «which?» named. Nothing here reads text.
"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_NOTED: list = []                       # (ask_id, among) in order, since the last advance
_FROZEN: dict = {"asks": [], "among": []}
_SEEN: dict = {"reply": None}


def note(ask_id: str, among=()) -> None:
    with _LOCK:
        _NOTED.append((str(ask_id or ""), tuple(str(t) for t in among or () if t)))


def turn_began(last_reply=None) -> None:
    """His turn starts. When a reply of ours closed a turn since the last read (`last_reply`, our last line in the
    window, is a new one), what was asked since becomes what this turn may answer; otherwise it is kept as it was."""
    with _LOCK:
        if last_reply is not None and (last_reply is _SEEN["reply"] or (isinstance(last_reply, dict)
                                                                         and last_reply.get("cut") and not _NOTED)):
            return                       # no new reply — or a cut one that asked nothing: the identity stands (F5)
        _SEEN["reply"] = last_reply
        which = max((i for i, (_a, among) in enumerate(_NOTED) if among), default=-1)   # our last «which?» rules (F2)
        _FROZEN.update(asks=[a for i, (a, among) in enumerate(_NOTED) if a and not among and i > which],
                       among=list(_NOTED[which][1]) if which >= 0 else [])
        _NOTED.clear()


def asked(ask: dict, waiting=None) -> bool:
    """This waiting row asked him since our last reply ALONE among the rows still `waiting` (all asked when None)."""
    still = {str(a.get("ask_id") or "") for a in waiting} if waiting is not None else set(_FROZEN["asks"])
    return set(_FROZEN["asks"]) & still == {str(ask.get("ask_id") or "")}


def named_by_which(ask: dict) -> bool:
    """A row our «which task?» named — it identifies the ROW, never one of its candidates."""
    return str(ask.get("task_id") or "") in _FROZEN["among"]


def reset() -> None:   # tests
    with _LOCK:
        _NOTED.clear()
        _FROZEN.update(asks=[], among=[])
        _SEEN["reply"] = None

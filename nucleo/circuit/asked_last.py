"""Which rows asked him since our last reply — by `ask_id`, never by the words we said (V2-893 L4).

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


def asked(ask: dict, waiting=None) -> bool:
    """This waiting row asked him since our last reply ALONE among the rows still `waiting` (all asked when None)."""
    still = {str(a.get("ask_id") or "") for a in waiting} if waiting is not None else set(_FROZEN["asks"])
    return set(_FROZEN["asks"]) & still == {str(ask.get("ask_id") or "")}


def reset() -> None:   # tests
    with _LOCK:
        _NOTED.clear()
        _FROZEN.update(asks=[], among=[])
        _SEEN["reply"] = None

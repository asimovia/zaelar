"""The card's answers in his language: one door to the UI pack (`widgets.mensajeria.<key>`), never a literal (V2-880)."""
from __future__ import annotations

from widgets.say import say as _app_say


def say(key: str, default: str, **kw) -> str:
    return _app_say("mensajeria", key, default, **kw)

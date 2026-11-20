"""Does this session go by the conversation manager? (V2-941, v3.1 §1.9 and the F1 plan §5)

The first that says something decides: (1) the SESSION — `conv=1` / `conv=0` in the app's URL, carried in the room's
metadata; (2) the ACCOUNT — the `conversation_manager` key of `config/settings.json`, false by default; (3) the
environment — `ZAELAR_CONVERSATION=1`, a development resource. It is read ONCE, when the session opens: a session
never changes path halfway. Going back is removing the key and reconnecting the voice, with no restart.

It fails CLOSED: switched on, a session only goes by the manager when every outside write of the install is held
(`ZAELAR_HOLD_OUTBOUND=all`), its language is chosen and the manager's configuration passes (`config.build`). Short
of that it takes the old path, and the decision says why — the caller emits it as an alert.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

ENV = "ZAELAR_CONVERSATION"
SETTING = "conversation_manager"
ON, OFF = frozenset({"1", "true", "yes", "on"}), frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class Decision:
    on: bool
    by: str                   # session | account | env | default
    why: str = ""             # switched on but refused: the reason the session takes the old path


def _flag(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v if v is not None else "").strip().lower()
    return True if s in ON else False if s in OFF else None


def asked(session: str | bool | None = None) -> tuple[bool, str]:
    """Is the manager asked for, and by whom — before the checks that may refuse it."""
    got = _flag(session)
    if got is not None:
        return got, "session"
    from config import settings
    got = _flag(settings.get(SETTING))
    if got is not None:
        return got, "account"
    got = _flag(os.getenv(ENV))
    if got is not None:
        return got, "env"
    return False, "default"


def refused() -> str:
    """Why a session asked for the manager may not take it now: '' when it may."""
    from connectors import exit as _exit
    if not all(_exit.held(lane) for lane in _exit.LANES):
        return f"{_exit.ENV} is not `all`: the manager runs only with every outside write held"
    if not (os.getenv("ZAELAR_LANGUAGE") or "").strip():
        return "no language chosen yet"
    from nucleo.conversation_host import config
    _cfg, problems = config.build()
    if problems:
        return "configuration refused: " + "; ".join(problems)
    return ""


def decide(session: str | bool | None = None) -> Decision:
    on, by = asked(session)
    if not on:
        return Decision(False, by)
    why = refused()
    return Decision(not why, by, why)

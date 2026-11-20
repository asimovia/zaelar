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
#: the manager for his TEXT only — the typed doors go by it, the voice stays on the old path
TEXT = "text"
TEXT_ONLY = "text only"           # why a voice session is off when the manager is asked for text only: a choice


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


def _source(session) -> tuple[object, str]:
    """The first that says something: the session's own flag, the account's key, the environment."""
    from config import settings
    for value, by in ((session, "session"), (settings.get(SETTING), "account"), (os.getenv(ENV), "env")):
        if _flag(value) is not None or str(value or "").strip().lower() == TEXT:
            return value, by
    return None, "default"


def asked(session: str | bool | None = None, voice: bool = False) -> tuple[bool, str]:
    """Is the manager asked for, and by whom — before the checks that may refuse it. `TEXT` asks it for the typed doors
    only: for the voice it is not asked."""
    value, by = _source(session)
    if str(value or "").strip().lower() == TEXT:
        return not voice, by
    return bool(_flag(value)), by


def text_only(session=None) -> bool:
    value, _by = _source(session)
    return str(value or "").strip().lower() == TEXT


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


def decide(session: str | bool | None = None, voice: bool = False) -> Decision:
    """`voice`: the decision for a voice session (`/api/voice/child/conv`) — off when the manager is asked for text only."""
    on, by = asked(session, voice)
    if not on:
        return Decision(False, by, TEXT_ONLY if voice and text_only(session) else "")
    why = refused()
    return Decision(not why, by, why)


def fall_back(session, why: str) -> None:
    """This session takes the old path from now on — said as an alert, never silently (the switch fails closed)."""
    from voice import observer
    if session is not None and hasattr(session, "__dict__"):
        session._conversation_switch = Decision(False, "fallback", why)
    observer.emit("alert", "conversation manager: this session goes the old way", text=why)


def typed_on(session=None) -> bool:
    """A TEXT door's question (a typed line): the session's own decision when it is the manager's, else the account's
    for text — with the manager asked for text only, a voice session on the old path still sends his typed lines to it."""
    if on(session):
        return True
    got = getattr(session, "_conversation_typed", None) if session is not None else None
    if got is None:
        got = decide(None)
        if session is not None and hasattr(session, "__dict__"):
            session._conversation_typed = got
    return got.on


def on(session=None) -> bool:
    """The door's question: does this line go by the manager? Decided ONCE per session (kept on the session object;
    the session's own `conv` flag, if it carries one, says first); with no session, the account's decision. A
    session asked for the manager and refused says why, once, as an alert."""
    got = getattr(session, "_conversation_switch", None) if session is not None else None
    if got is None:
        got = decide(getattr(session, "conv_flag", None) if session is not None else None)
        if session is not None and hasattr(session, "__dict__"):   # one with no attributes is decided at every line
            session._conversation_switch = got
        if got.why and (session is None or getattr(session, "_conversation_switch", None) is got):
            from voice import observer
            observer.emit("alert", "conversation manager refused", text=got.why, extra={"by": got.by})
    return got.on

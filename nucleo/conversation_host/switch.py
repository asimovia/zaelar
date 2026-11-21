"""The conversation manager is the only path (INI-078 F2, the unplug): every session goes by it.

There is no mode and nothing to fall back to. The manager still runs only when it may: every outside write of the
install held but the lanes the manager itself carries, each with his yes (`declared.json` `sends_by`;
`ZAELAR_HOLD_OUTBOUND=all` or `all,-owner`), its language chosen and its configuration passing (`config.build`). Short
of that the session answers NOTHING — the reason is put on his screen as an alert (`silent`), never an old path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    on: bool
    by: str = "manager"
    why: str = ""             # the manager may not run now: the reason on his screen, and silence


def refused() -> str:
    """Why a session asked for the manager may not take it now: '' when it may."""
    import sys
    entry = sys.modules.get("nucleo.conversation_host.entry")
    if entry is not None and entry.broken():
        return "the conversation could not open a moment ago"
    from connectors import exit as _exit
    from nucleo.conversation_host.declared import declared
    carried = set(declared().get("sends_by") or ())          # the lanes the manager carries, each with his yes
    if not all(_exit.held(lane) for lane in _exit.LANES - carried):
        return (f"{_exit.ENV} holds too little: the manager runs only with every outside write held but the lanes it "
                f"carries ({', '.join(sorted(carried)) or 'none'})")
    if not (os.getenv("ZAELAR_LANGUAGE") or "").strip():
        return "no language chosen yet"
    from nucleo.conversation_host import config
    _cfg, problems = config.build()
    if problems:
        return "configuration refused: " + "; ".join(problems)
    return ""


def decide(session=None, voice: bool = False) -> Decision:
    """The manager, always; `on` False only while it may not run (`why`). `session`/`voice` are what a caller has."""
    why = refused()
    return Decision(not why, "manager", why)


def silent(session, why: str) -> None:
    """This session may not be answered now: the reason on his screen (an alert), and silence — nothing else answers."""
    from voice import observer
    if session is not None and hasattr(session, "__dict__"):
        session._conversation_switch = Decision(False, "refused", why)
    observer.emit("alert", "the conversation cannot answer now", text=why)
    from nucleo.conversation_host import wall
    wall.sweep("refused")                        # a line the manager left open on the wall would never be closed


def on(session=None) -> bool:
    """The door's question: may the manager take this line now? Decided ONCE per session (kept on the session object);
    with no session, now. A session the manager may not take says why, once, on his screen."""
    got = getattr(session, "_conversation_switch", None) if session is not None else None
    if got is None:
        got = decide()
        if session is not None and hasattr(session, "__dict__"):   # one with no attributes is decided at every line
            session._conversation_switch = got
        if got.why and (session is None or getattr(session, "_conversation_switch", None) is got):
            from voice import observer
            observer.emit("alert", "the conversation cannot answer now", text=got.why)
    return got.on


def holds_the_voice() -> bool:
    """Does a voice session of the manager hold the voice now? Read off the host only when it is loaded: switched off
    it never is, and the answer is False with nothing imported."""
    import sys
    owed = sys.modules.get("nucleo.conversation_host.owed")
    return bool(owed is not None and owed.voice_live())


def legacy_call(counter: str) -> bool:
    """A door of the old turn reached while the manager holds the voice: counted on the proof (a must-be-zero, said by
    `GET /api/debug/conversation/<session>`). True when it was."""
    if not holds_the_voice():
        return False
    from nucleo.conversation_host import boot, proof
    proof.note(boot.account(), counter)
    return True

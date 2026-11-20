"""The conversation of an account, built with the engine's ports (V2-941, B5): its store on `zaelar.db`, the voice's
model, the read tools, the state readers, the record, his rules, the clock, the observer — inside its own thread
(`runtime.py`), one per account (`sessions.py`). The account is this installation's identity
(`observability.identity.user_id`).
"""
from __future__ import annotations

from typing import Callable

ACCOUNT_OWNER = "host"


def account() -> str:
    from observability import identity
    return identity.user_id()


def make(listeners: tuple = (), said: Callable | None = None) -> Callable:
    """The factory the runtime calls INSIDE its thread."""
    def _make():
        from conversation import build
        from memory import db as _db
        from nucleo.conversation_host import config, prefix, proof, record
        from nucleo.conversation_host.clock import SystemClock
        from nucleo.conversation_host.memory_read import MemoryRead
        from nucleo.conversation_host.model import FastModel
        from nucleo.conversation_host.mouth import WallMouth
        from nucleo.conversation_host.owed import NoticesOwed
        from nucleo.conversation_host.words import PackWords
        from nucleo.conversation_host.store import ZaelarStore
        from nucleo.conversation_host.telemetry import ObserverTelemetry
        from nucleo.conversation_host.tools_read import ReadTools
        clock = SystemClock()
        cfg, _problems = config.build()                  # the switch refused a session whose config does not pass
        tools = ReadTools()
        from nucleo.conversation_host import entry, voice_mouth
        mouth = WallMouth(clock, said, voice=voice_mouth, ack_later=entry.ack)
        conv = build(account=account(), owner=ACCOUNT_OWNER, model=FastModel(), tools=tools,
                     store=ZaelarStore(_db.get_db()), memory=MemoryRead(), clock=clock, mouth=mouth,
                     telemetry=proof.Counting(ObserverTelemetry(listeners), account()), config=cfg, prefix=prefix.current(tools.catalog()),
                     prefs=config.prefs, record=record.MemoryRecord(), owed=NoticesOwed(),
                     words=PackWords())
        mouth.ack = conv.ack
        conv.recover()
        return conv
    return _make

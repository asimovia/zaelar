"""A bench case's world outlives the threads its turns started (2026-11-12, the multi-turn bench).

The whisperer (V2-889 F2) runs on its own thread off `turn.closed`, after the turn returned. The last turn of a case
returned, the case gave the operator's keys and database back, and the whisper thread then resolved its key: DeepSeek
answered 401 to the `local` sentinel, and its event would have been written into the install's database. The case now
waits for those threads, bounded by the whisperer's own clock, before it restores anything.

Disarm: drop the wait at the top of `Isolated.__exit__` → the thread reads the restored environment → red.
"""
from __future__ import annotations

import os
import threading
import time

from tests.platform import turn_harness as H


def test_the_wait_is_bounded_by_the_whisperers_clock(monkeypatch):
    from nucleo.whisper import run as whisper
    asked = {}
    monkeypatch.setattr(whisper, "wait", lambda timeout=5.0: asked.setdefault("timeout", timeout) and True)
    assert H._await_the_turns_own_threads() is True
    assert asked["timeout"] == 2 * whisper.DEFAULT_TIMEOUT_S + whisper.BRIEF_WAIT_S

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


def test_a_thread_the_turn_started_reads_the_cases_world_until_it_ends(monkeypatch):
    from nucleo.turn.whisper import run as whisper
    seen: dict = {}
    before = os.environ.get("ZAELAR_DB")
    with H.Isolated("es") as iso:
        lent = os.environ.get("ZAELAR_DB")

        def late_whisper():
            time.sleep(0.4)                    # the reasoner's call resolves its key after the turn returned
            seen["db"] = os.environ.get("ZAELAR_DB")

        th = threading.Thread(target=late_whisper, daemon=True)
        monkeypatch.setitem(whisper._S, "threads", [th])
        th.start()
        assert iso.tmp and lent and lent.startswith(iso.tmp)
    assert seen.get("db") == lent, f"the whisper thread read {seen.get('db')!r} — the case's world was gone"
    assert os.environ.get("ZAELAR_DB") == before


def test_the_wait_is_bounded_by_the_whisperers_clock(monkeypatch):
    from nucleo.turn.whisper import run as whisper
    asked = {}
    monkeypatch.setattr(whisper, "wait", lambda timeout=5.0: asked.setdefault("timeout", timeout) and True)
    assert H._await_the_turns_own_threads() is True
    assert asked["timeout"] == 2 * whisper.DEFAULT_TIMEOUT_S + whisper.BRIEF_WAIT_S

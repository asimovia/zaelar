"""The conversation's own thread (V2-941): its one writer and its event loop.

The `Conversation` lives in this thread from the moment it is switched on. Its writes to `conv_*` leave from here
only, by the shared connection under its lock — a write that waits for that lock delays this thread's answer and
nothing else; the server's loop never waits on it (the lock already stopped that loop once: a reader waited 7.1 s).

  · what arrives from the server's loop (a text, a button, a voice fact) is handed over with `submit`, which runs it
    here and returns a future the caller may await or ignore;
  · the manager's own timer (`Conversation.keep_time`) runs here, and so does the hourly prune of what is final and
    older than the horizon (`memory.api.conv.prune`) — in this thread, never in another writer's;
  · reads outside a transaction go through this thread's read-only connection, which never waits for a writer.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from typing import Any, Callable

from memory.api import conv as cs

logger = logging.getLogger("zaelar.conversation_host.runtime")

PRUNE_EVERY_S = 3600          # the cadence the pulse consolidates and prunes the tasks at
MAX_AGE_DAYS = 30


class ConversationRuntime:
    """`make()` builds the `Conversation` INSIDE the thread (its store, its clock, its ports)."""

    def __init__(self, make: Callable[[], Any], *, prune_every_s: float = PRUNE_EVERY_S,
                 max_age_days: int = MAX_AGE_DAYS, keep_time_ms: int = 250, db=None) -> None:
        self._make, self._prune_every, self._max_age, self._keep = make, prune_every_s, max_age_days, keep_time_ms
        self._db = db
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conv: Any = None
        self.pruned: list[int] = []            # rows each prune removed (the last few), for the observer and tests
        self.error: BaseException | None = None

    # ── life ──────────────────────────────────────────────────────────────────────────────────────────────────────
    def start(self, timeout_s: float = 10.0) -> "ConversationRuntime":
        self._thread = threading.Thread(target=self._main, name="conversation", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout_s):
            raise TimeoutError("the conversation's thread did not start")
        if self.error is not None:
            raise RuntimeError("the conversation's thread failed to start") from self.error
        return self

    def _main(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.conv = self._make()
        except BaseException as e:  # noqa: BLE001 — said to the starter, who raises it
            self.error = e
            self._ready.set()
            return
        self._timer = self.loop.create_task(self.conv.keep_time(self._keep))
        self.loop.call_later(self._prune_every, self._prune_tick)
        self._ready.set()
        try:
            self.loop.run_forever()
        finally:
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            self.loop.run_until_complete(asyncio.sleep(0))
            self.loop.close()

    def stop(self, timeout_s: float = 10.0) -> None:
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread is not None:
            self._thread.join(timeout_s)

    @property
    def thread_id(self) -> int | None:
        return self._thread.ident if self._thread else None

    # ── in ───────────────────────────────────────────────────────────────────────────────────────────────────────
    def submit(self, fn: Callable[[Any], Any]) -> concurrent.futures.Future:
        """Run `fn(conversation)` in the conversation's thread — a coroutine is awaited there — and pump after it, as
        the live loop does when something was accepted. Returns a future of its result."""
        async def job():
            out = fn(self.conv)
            if asyncio.iscoroutine(out):
                out = await out
            if self.conv.pumpable:
                await self.conv.pump()
            return out
        return asyncio.run_coroutine_threadsafe(job(), self.loop)

    # ── the hourly prune, in this thread ─────────────────────────────────────────────────────────────────────────
    def prune_now(self) -> int:
        gone = cs.prune(self._max_age, int(time.time() * 1000), db=self._db)
        self.pruned = (self.pruned + [gone])[-24:]
        return gone

    def _prune_tick(self) -> None:
        try:
            self.prune_now()
        except Exception as e:  # noqa: BLE001 — a failed prune is said and retried at the next tick
            logger.warning(f"conversation: the hourly prune failed ({type(e).__name__}: {e})")
        self.loop.call_later(self._prune_every, self._prune_tick)

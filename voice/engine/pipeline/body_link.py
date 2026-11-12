"""body_link.py — the voice process's one line to the body (V2-891).

When the voice runs in its OWN process (`python -m voice.engine`), everything the session observes that the brain
reads — its VAD edges, its transcripts, the room's data packets, its metrics, every observer line — is a fact the
BODY must hold, because the body runs the turn. This module carries those facts there, and nothing else:

  · `send(event)` queues one event; ONE sender drains the queue in order, in batches, to `POST /api/voice/child/events`.
    A batch that does not land within `timeout_s` is DROPPED and counted, never retried into a backlog: the ear
    must never wait on the body (a body paging in from swap is exactly the case this process exists for). The facts
    the body must not lose — a session's start/close, his transcripts, the items — are asked ONCE more (E0).
  · while the body does not answer, the sender opens at most ONE connection per `RETRY_GAP_S` (E0): measured
    2026-11-12, a batch per failure filled a stopped body's TCP backlog in 31 s and the turn found it «unreachable».
  · `ahead()` — a request that must follow the facts queued before it (the turn, the kickoff) TAKES them off the
    line and carries them (`events`): the body replays them first, so it reads «he stopped talking» before the turn
    that followed (the order a single process gave for free) whatever the sender was waiting for; `back()` returns
    them to the front when the request never reached the body.
  · `post()` / `stream()` — the request/response calls (the kickoff decision, the turn's stream).

TWO LOOPS. The LiveKit job runs on its own thread and loop (the THREAD executor), the worker and the control routes
on the main one: the sender lives on the loop that `start()`ed it, `send()`, `ahead()` and `back()` are safe from
either (one lock over the queue and the in-flight mark), and every loop gets its own HTTP session — an aiohttp
session is bound to the loop that made it; from the other one every turn fails with «attached to a different loop».

A batch that carries a session's start or close is retried once at the front of the queue: those two facts decide
what the body registers, and a body still warming up at boot answered the first batch late (measured).

Every call carries the token the body handed this process at spawn (`ZAELAR_VOICE_TOKEN`), and the body only
answers it from loopback. Never raises into the voice: a failed call is a counted miss and an empty answer.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import deque

from loguru import logger

TOKEN_ENV = "ZAELAR_VOICE_TOKEN"
HEADER = "x-zaelar-voice-token"
EVENTS_PATH = "/api/voice/child/events"
RETRY_GAP_S = 1.0                                 # one connection a second while the body does not answer (E0)
RETRIED = ("session", "transcript", "item")       # the facts asked once more at the front of the queue


def body_url() -> str:
    """Where the body listens: `ZAELAR_BODY_URL`, else this host's loopback on the app port."""
    explicit = (os.getenv("ZAELAR_BODY_URL") or "").strip().rstrip("/")
    return explicit or f"http://127.0.0.1:{(os.getenv('PORT') or '43917').strip()}"


class BodyLink:
    def __init__(self, base: str | None = None, token: str | None = None, *, timeout_s: float = 0.2,
                 max_batch: int = 256, max_queue: int = 4096) -> None:
        self.base = (base or body_url()).rstrip("/")
        self.token = token if token is not None else (os.getenv(TOKEN_ENV) or "")
        self.timeout_s = float(timeout_s)
        self.max_batch = int(max_batch)
        self._q: deque = deque(maxlen=int(max_queue))
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._flying = False                  # a batch is in the sender's hands (out of the queue, not yet answered)
        self._task: asyncio.Task | None = None
        self._sessions: dict = {}             # id(loop) → (loop, aiohttp session): one per loop
        self._fail_streak = 0                 # batches failed in a row: >0 paces the sender to one try per gap
        self._last_try = 0.0
        self.stats = {"sent": 0, "dropped": 0, "batches": 0, "failed_batches": 0, "overtaken": 0}

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Bind to the running loop and start the sender. Idempotent per loop."""
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._task is not None and not self._task.done():
            return
        self._loop = loop
        self._wake, self._flying = asyncio.Event(), False
        self._task = loop.create_task(self._run(), name="voice-body-link")

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
        here = asyncio.get_running_loop()
        for key, (loop, sess) in list(self._sessions.items()):
            if loop is here:
                try:
                    await sess.close()
                except Exception as _swallowed:  # noqa: BLE001
                    logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            self._sessions.pop(key, None)

    def _headers(self) -> dict:
        return {HEADER: self.token, "content-type": "application/json"}

    def _http(self):
        import aiohttp
        loop = asyncio.get_running_loop()
        got = self._sessions.get(id(loop))
        if got is None or got[0] is not loop or got[1].closed:
            for key, (lp, _s) in list(self._sessions.items()):
                if lp.is_closed():
                    self._sessions.pop(key, None)
            got = (loop, aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=16)))
            self._sessions[id(loop)] = got
        return got[1]

    # ── the ordered event channel ───────────────────────────────────────────────────────────────────────────
    def send(self, event: dict) -> None:
        """Queue one event, from any thread. Never blocks, never raises."""
        try:
            ev = dict(event)
            ev.setdefault("at", time.time())
            with self._lock:
                if len(self._q) == self._q.maxlen:
                    self.stats["dropped"] += 1      # the oldest falls off: a body that cannot keep up loses the oldest
                self._q.append(ev)
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                self._kick()
            else:
                loop.call_soon_threadsafe(self._kick)
        except Exception as e:  # noqa: BLE001 — the ear never dies of its own report
            logger.debug(f"body_link.send: {e!r}")

    def _kick(self) -> None:
        if self._wake is not None:
            self._wake.set()

    async def ahead(self, step_s: float = 0.003) -> list:
        """Every fact queued so far, TAKEN off the line for the caller's request to carry: the order is kept by the
        request itself, never by a wait that happens to outlast the sender's. A batch already in the sender's hands
        is waited for as long as its own POST may take (`timeout_s`, twice: the POST, then its hand-back); past that
        the request goes ahead of it and says so (`stats["overtaken"]`). Polled on the CALLER's loop."""
        deadline = time.monotonic() + 2 * self.timeout_s
        while True:
            with self._lock:
                if not self._flying or time.monotonic() >= deadline:
                    out, late = list(self._q), self._flying
                    self._q.clear()
                    break
            await asyncio.sleep(step_s)
        if late:
            self.stats["overtaken"] += 1
            logger.warning("voice→body: a batch in flight was not back by its own deadline — the request overtakes it")
        return out

    def back(self, events: list) -> None:
        """The request that carried `events` never reached the body: they return to the FRONT of the line, in order."""
        with self._lock:
            self._q.extendleft(reversed(events))
        if events and self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._kick)

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while True:
                await self._pace()                # BEFORE the batch leaves the queue: a paced fact is still on the line
                with self._lock:
                    batch = [self._q.popleft() for _ in range(min(self.max_batch, len(self._q)))]
                    self._flying = bool(batch)
                if not batch:
                    break
                await self._deliver(batch)
                self._flying = False              # delivered, or its retried facts are back at the front

    async def _pace(self) -> None:
        """While the body is failing, wait out the gap since the last try: one connection per `RETRY_GAP_S`."""
        if self._fail_streak:
            wait = RETRY_GAP_S - (time.monotonic() - self._last_try)
            if wait > 0:
                await asyncio.sleep(wait)

    async def _deliver(self, batch: list) -> None:
        self.stats["batches"] += 1
        self._last_try = time.monotonic()
        try:
            import aiohttp
            async with self._http().post(self.base + EVENTS_PATH, data=json.dumps({"events": batch}, default=str),
                                         headers=self._headers(),
                                         timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as r:
                if r.status >= 300:
                    raise RuntimeError(f"HTTP {r.status}")
            self.stats["sent"] += len(batch)
            self._fail_streak = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — dropped and counted: the ear never waits on the body
            self._fail_streak += 1
            again = [ev for ev in batch if ev.get("k") in RETRIED and not ev.get("_retried")]
            if again:                       # a session's start/close, his words, the items: asked once more
                with self._lock:
                    for ev in reversed(again):
                        self._q.appendleft({**ev, "_retried": True})
            self.stats["dropped"] += len(batch) - len(again)
            self.stats["failed_batches"] += 1
            if self.stats["failed_batches"] in (1, 10, 100) or self.stats["failed_batches"] % 1000 == 0:
                logger.warning(f"voice→body: {len(batch)} events dropped ({e!r}); "
                               f"{self.stats['dropped']} dropped so far")

    # ── request / response ──────────────────────────────────────────────────────────────────────────────────
    async def post(self, path: str, payload: dict, timeout_s: float = 5.0) -> dict:
        """One JSON call to the body. `{}` on any failure."""
        try:
            import aiohttp
            async with self._http().post(self.base + path, data=json.dumps(payload, default=str),
                                         headers=self._headers(),
                                         timeout=aiohttp.ClientTimeout(total=timeout_s)) as r:
                if r.status >= 300:
                    logger.warning(f"voice→body {path}: HTTP {r.status}")
                    return {}
                return await r.json()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning(f"voice→body {path}: {e!r}")
            return {}

    async def stream(self, path: str, payload: dict, connect_s: float = 3.0):
        """NDJSON lines from the body, one dict each, as they arrive. Closing the iterator closes the connection —
        which is how the body learns the turn was cancelled (a barge-in, a preemptive draft thrown away)."""
        import aiohttp
        async with self._http().post(self.base + path, data=json.dumps(payload, default=str), headers=self._headers(),
                                     timeout=aiohttp.ClientTimeout(total=None, sock_connect=connect_s)) as r:
            if r.status >= 300:
                raise RuntimeError(f"body {path}: HTTP {r.status}")
            async for raw in r.content:
                line = raw.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    logger.debug(f"voice←body: unreadable line {line[:80]!r}")


_LINK: dict = {"link": None}


def get() -> BodyLink:
    """This process's link (one per voice process)."""
    if _LINK["link"] is None:
        _LINK["link"] = BodyLink()
    return _LINK["link"]


def use(link: BodyLink | None) -> None:
    """Tests hand in their own link (or None to forget it)."""
    _LINK["link"] = link


def active() -> bool:
    """True inside the voice process: its observer lines and session facts travel to the body."""
    return (os.getenv("ZAELAR_VOICE_ROLE") or "").strip().lower() == "child"

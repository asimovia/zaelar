"""body_link.py — the voice process's one line to the body (V2-891).

When the voice runs in its OWN process (`python -m voice.engine`), everything the session observes that the brain
reads — its VAD edges, its transcripts, the room's data packets, its metrics, every observer line — is a fact the
BODY must hold, because the body runs the turn. This module carries those facts there, and nothing else:

  · `send(event)` queues one event; ONE sender drains the queue in order, in batches, to `POST /api/voice/child/events`.
    A batch that does not land within `timeout_s` is DROPPED and counted, never retried into a backlog: the ear
    must never wait on the body (a body paging in from swap is exactly the case this process exists for).
  · `flush(max_s)` — a turn waits, bounded, for the events queued before it, so the body reads «he stopped
    talking» before it reads the turn that followed (the order a single process gave for free).
  · `post()` / `stream()` — the request/response calls (the kickoff decision, the turn's stream).

TWO LOOPS. The LiveKit job runs on its own thread and loop (the THREAD executor), the worker and the control routes
on the main one: the sender lives on the loop that `start()`ed it, `send()` and `flush()` are safe from either (a
thread-safe queue and idle flag), and every loop gets its own HTTP session — an aiohttp session is bound to the loop
that made it, and using it from the other one fails every turn with «attached to a different loop» (measured).

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
        self._idle = threading.Event()
        self._idle.set()
        self._task: asyncio.Task | None = None
        self._sessions: dict = {}             # id(loop) → (loop, aiohttp session): one per loop
        self.stats = {"sent": 0, "dropped": 0, "batches": 0, "failed_batches": 0}

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Bind to the running loop and start the sender. Idempotent per loop."""
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._task is not None and not self._task.done():
            return
        self._loop = loop
        self._wake = asyncio.Event()
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
                    pass
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
                self._idle.clear()
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

    def pending(self) -> int:
        with self._lock:
            return len(self._q)

    async def flush(self, max_s: float = 0.2, step_s: float = 0.003) -> bool:
        """Wait, at most `max_s`, until every event queued so far has been handed to the body. True if it emptied.
        Polled on the CALLER's loop (the session's), so it never touches the sender's loop."""
        deadline = time.monotonic() + max_s
        while not self._idle.is_set():
            if self._task is None or time.monotonic() >= deadline:
                return self._idle.is_set()
            await asyncio.sleep(step_s)
        return True

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            while True:
                with self._lock:
                    batch = [self._q.popleft() for _ in range(min(self.max_batch, len(self._q)))]
                if not batch:
                    break
                await self._deliver(batch)
            with self._lock:
                if not self._q:
                    self._idle.set()

    async def _deliver(self, batch: list) -> None:
        self.stats["batches"] += 1
        try:
            import aiohttp
            async with self._http().post(self.base + EVENTS_PATH, data=json.dumps({"events": batch}, default=str),
                                         headers=self._headers(),
                                         timeout=aiohttp.ClientTimeout(total=self.timeout_s)) as r:
                if r.status >= 300:
                    raise RuntimeError(f"HTTP {r.status}")
            self.stats["sent"] += len(batch)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — dropped and counted: the ear never waits on the body
            again = [ev for ev in batch if ev.get("k") == "session" and not ev.get("_retried")]
            if again:                       # a session's start/close decides what the body registers: once more
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

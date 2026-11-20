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

LATEST WINS for the live caption (2026-11-18). An interim — his words while he is still speaking — is only worth its
newest version, and it was dropped with every failed batch: measured on a swapping host, ~90 failed batches in
18 min with the body stalled 1-8.7 s, and the caption on the wall froze for exactly those seconds. Now a newer
interim REPLACES an older one still queued (`send`), the newest interim of a failed batch goes back to the front
unless something newer already says more (a newer interim, or his final words), and while only such a caption
waits the sender retries after `CAPTION_GAP_S` instead of the full `RETRY_GAP_S`. An older interim never reaches
the body after a newer one.

THE EAR'S LANE IS LOSSLESS (V2-941, B8). The facts the conversation manager's ear reads (`ear_feed.py`) cannot be
dropped the way a batch is: a lost final word is a sentence never whole. They ride the same line in a queue of their
own (`send_ear`), numbered (`seq`, with this process's `boot`), at the FRONT of every batch, and they leave that queue
only when the body has answered the batch that carried them — a failed batch carries them again, never marked
«retried». The queue has a ceiling (`EAR_MAX`, some 30 s of facts): past it the newest facts are not queued but
DECLARED lost, by one `gap` fact in their place that grows while the hole lasts — so the ear ends what it was hearing
incomplete (`link_gap`) and the run asks for it again. A hole is never silent and leaves nothing waiting.

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
CAPTION_GAP_S = 0.4                               # the retry gap while only a live caption waits (latest wins)
EAR_MAX = 1500                                    # the ear's facts held for the body: ~30 s of a stalled body


def caption_key(ev: dict):
    """The identity of a LATEST-WINS fact (his interim words, by speaker), or None for every other fact."""
    if ev.get("k") == "emit" and ev.get("kind") == "interim":
        return ("emit", ev.get("role") or "")
    if ev.get("k") == "transcript" and not ev.get("final"):
        return ("transcript", "")
    return None


def _says_more(ev: dict, key) -> bool:
    """Does `ev`, queued AFTER a caption of `key`, make it stale? A newer caption of the same speaker, or his final
    words (on either channel), which are what the caption was a preview of."""
    if caption_key(ev) == key:
        return True
    if ev.get("k") == "transcript" and ev.get("final"):
        return True
    return ev.get("k") == "emit" and ev.get("kind") == "transcript" and ev.get("role") == "user"


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
        self.stats = {"sent": 0, "dropped": 0, "batches": 0, "failed_batches": 0, "overtaken": 0, "coalesced": 0,
                      "ear_sent": 0, "ear_lost": 0}
        import uuid
        self._ear: deque = deque()             # the ear's facts, in `seq` order, until the body answered their batch
        self._ear_seq, self._ear_boot = 0, uuid.uuid4().hex[:12]

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
            key = caption_key(ev)
            with self._lock:
                if key is not None:                 # latest wins: the older caption still queued is superseded
                    older = [x for x in self._q if caption_key(x) == key]
                    for x in older:
                        self._q.remove(x)
                    self.stats["coalesced"] += len(older)
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

    def send_ear(self, fact: dict) -> None:
        """Queue one fact of the ear, from any thread: numbered, kept until the body answered it, never dropped
        unsaid. Past `EAR_MAX` the fact is not kept but declared: one `gap` fact grows in its place."""
        try:
            with self._lock:
                self._ear_seq += 1
                ev = {**fact, "k": "ear", "seq": self._ear_seq, "boot": self._ear_boot}
                last = self._ear[-1] if self._ear else None
                if len(self._ear) < EAR_MAX:
                    self._ear.append(ev)
                elif last is not None and last.get("t") == "gap" and not last.get("_flying"):
                    last["covers"][1] = self._ear_seq
                    last["streams"] = sorted(set(last["streams"]) | {str(fact.get("stream") or "")})
                    self.stats["ear_lost"] += 1
                else:
                    self._ear.append({"k": "ear", "t": "gap", "seq": self._ear_seq, "boot": self._ear_boot,
                                      "covers": [self._ear_seq, self._ear_seq],
                                      "streams": [str(fact.get("stream") or "")], "t_ms": int(time.time() * 1000)})
                    self.stats["ear_lost"] += 1
            loop = self._loop
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self._kick)
        except Exception as e:  # noqa: BLE001 — the ear never dies of its own report
            logger.debug(f"body_link.send_ear: {e!r}")

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
                    ear = list(self._ear)[: self.max_batch]      # at the front, and still in the queue until answered
                    for ev in ear:
                        ev["_flying"] = True
                    batch = [self._q.popleft() for _ in range(min(self.max_batch - len(ear), len(self._q)))]
                    self._flying = bool(batch)
                if not batch and not ear:
                    break
                ok = await self._deliver([{k: v for k, v in ev.items() if k != "_flying"} for ev in ear] + batch)
                with self._lock:
                    for ev in ear:
                        ev.pop("_flying", None)
                    if ok and ear:                   # answered: they leave the lane; unanswered, they ride again
                        while self._ear and self._ear[0]["seq"] <= ear[-1]["seq"]:
                            self._ear.popleft()
                        self.stats["ear_sent"] += len(ear)
                self._flying = False              # delivered, or its retried facts are back at the front

    async def _pace(self) -> None:
        """While the body is failing, wait out the gap since the last try: one connection per `RETRY_GAP_S` — or per
        `CAPTION_GAP_S` while all that waits is a live caption, which is stale a second later."""
        if self._fail_streak:
            with self._lock:
                only_captions = bool(self._q) and all(caption_key(ev) is not None for ev in self._q)
            gap = CAPTION_GAP_S if only_captions else RETRY_GAP_S
            wait = gap - (time.monotonic() - self._last_try)
            if wait > 0:
                await asyncio.sleep(wait)

    async def _deliver(self, batch: list) -> bool:
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
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — dropped and counted: the ear never waits on the body
            self._fail_streak += 1
            back, stale = [], 0
            with self._lock:
                later = list(self._q)                # queued since this batch left: all newer than it
                for i, ev in enumerate(batch):
                    if ev.get("k") == "ear":
                        continue                     # the ear's lane keeps its own: carried again, never dropped
                    key = caption_key(ev)
                    if key is None:
                        # a session's start/close, his words, the items: asked once more
                        if ev.get("k") in RETRIED and not ev.get("_retried"):
                            back.append({**ev, "_retried": True})
                        continue
                    # latest wins: a caption goes back unless what came after it — in this batch or queued
                    # since — already says more. Never marked retried: it is asked until it lands or is replaced.
                    if any(_says_more(x, key) for x in batch[i + 1:]) or any(_says_more(x, key) for x in later):
                        stale += 1
                        continue
                    back.append(ev)
                for ev in reversed(back):
                    self._q.appendleft(ev)
            self.stats["coalesced"] += stale
            ears = sum(ev.get("k") == "ear" for ev in batch)
            self.stats["dropped"] += len(batch) - ears - len(back) - stale
            self.stats["failed_batches"] += 1
            if self.stats["failed_batches"] in (1, 10, 100) or self.stats["failed_batches"] % 1000 == 0:
                logger.warning(f"voice→body: {len(batch) - ears - len(back)} of {len(batch)} events dropped ({e!r}); "
                               f"{self.stats['dropped']} dropped so far")
            return False

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

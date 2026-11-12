"""voice/child_process.py — the body starts, watches and restarts the voice's own process (V2-891).

`VoiceChild` is shaped like the embedded LiveKit `AgentServer` where the engine reads one — `run(devmode)`,
`aclose()`, `id`, `_closed`, `_connecting` — so the heartbeat, the recycle (`nucleo/pulse/voice_recycle.py`) and the
token door (`voice_recycle.starting`) treat the voice process exactly as they treat the embedded worker: a recycle
is a bounded close of this process and a verified start of the next one.

`run()` spawns `python -m voice.engine` (never a fork: a subprocess, a fresh interpreter, on macOS and Linux alike)
with what it needs and nothing of the body's secrets beyond its own env: the app port (its worker port is that +1000),
the body's loopback address, its parent pid (it exits when the body does) and a per-spawn token (the body's routes
for it answer only that token; no Brain Worker inherits it). Then it reads the process's `/voice/status` every
`status_s`: LiveKit's worker id (registered or not), whether a session is live, its RSS.

Priorities (`nucleo/pulse/priority.py`): the voice process asks for nice 0 and the lowest OOM score its privileges
allow, the body takes nice 5 once its first voice is up. An unprivileged host cannot raise a priority back, so a
voice process RESTARTED by an already-niced body runs at the body's nice; the event says so (`nice` in the status).

`ZAELAR_VOICE_EMBEDDED=1` keeps the voice inside the body (the LiveKit job as a thread, as before V2-891).
"""
from __future__ import annotations

import asyncio
import os
import secrets
import signal
import sys
import time

from loguru import logger

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATE: dict = dict(token="", child=None, body_niced=False)
#: The header the voice process presents its token in (the same name `body_link.HEADER` carries; one value).
HEADER = "x-zaelar-voice-token"
#: The env keys `_env` sets for the process it spawns besides the `ZAELAR_VOICE_*` ones (they name that process).
SPAWN_KEYS = frozenset(("ZAELAR_BODY_URL", "ZAELAR_WORKER_PORT"))


def embedded() -> bool:
    """The voice stays a thread of the body (the pre-V2-891 shape) — the disarm, and the escape hatch."""
    return (os.getenv("ZAELAR_VOICE_EMBEDDED") or "").strip().lower() in ("1", "true", "yes", "on")


def token() -> str:
    """The token of the voice process this body started last ('' when it started none)."""
    return _STATE["token"]


def current():
    return _STATE["child"]


def _pidfile() -> str:
    d = os.path.join(_ROOT, ".meshkore", ".runtime")
    return os.path.join(d, f"voice-{os.getenv('PORT') or '43917'}.pid")


def _reap_orphan(path: str) -> None:
    """A voice process left by a body that died hard still holds the worker port: end it before starting ours."""
    try:
        pid = int(open(path, encoding="ascii").read().strip() or 0)
    except (OSError, ValueError) as _swallowed:
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return
    if pid <= 0 or pid == os.getpid():
        return
    try:
        import psutil
        p = psutil.Process(pid)
        if "voice.engine" not in " ".join(p.cmdline()) or p.ppid() == os.getpid():
            return
        logger.warning(f"voice process: ending an orphan voice process {pid} (its body is gone)")
        p.terminate()
        p.wait(timeout=5)
    except Exception as _swallowed:  # noqa: BLE001 — gone already, or not ours
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        pass


class VoiceChild:
    def __init__(self, *, port: int | None = None, status_s: float = 0.5, stop_s: float = 5.0) -> None:
        from voice.engine.pipeline.agent import worker_health_port
        from voice.remote_session import ChildClient
        self.app_port = int(os.getenv("PORT") or "43917")
        self.port = int(port or worker_health_port())
        self.token = secrets.token_urlsafe(24)
        self.client = ChildClient(f"http://127.0.0.1:{self.port}", self.token)
        self.status_s, self.stop_s = float(status_s), float(stop_s)
        self.id = "unregistered"
        self._closed = True
        self._connecting = False
        self._http_server = None                 # the recycle releases an embedded worker's port; this one has none
        self._proc: asyncio.subprocess.Process | None = None
        self.status: dict = {}
        self.started_at = 0.0

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def rss_mb(self) -> float:
        return float(self.status.get("rss_mb") or 0.0)

    def live(self) -> bool:
        return bool(self.status.get("live"))

    def _env(self) -> dict:
        from voice.engine.pipeline import body_link
        env = dict(os.environ)
        env.update(dict(ZAELAR_VOICE_ROLE="child", ZAELAR_BODY_URL=f"http://127.0.0.1:{self.app_port}",
                        ZAELAR_VOICE_PARENT=str(os.getpid()), ZAELAR_WORKER_PORT=str(self.port),
                        PORT=str(self.app_port)))
        env[body_link.TOKEN_ENV] = self.token
        env.pop("ZAELAR_VOICE_EMBEDDED", None)
        return env

    async def _spawn(self) -> None:
        pidfile = _pidfile()
        _reap_orphan(pidfile)
        self._proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "voice.engine", cwd=_ROOT,
                                                          env=self._env())
        self.started_at = time.time()
        try:
            os.makedirs(os.path.dirname(pidfile), exist_ok=True)
            with open(pidfile, "w", encoding="ascii") as fh:
                fh.write(str(self._proc.pid))
        except OSError as _swallowed:
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass
        _STATE["token"], _STATE["child"] = self.token, self
        from voice import remote_session
        remote_session.use_client(self.client)
        from nucleo.pulse import priority
        priority.apply(self._proc.pid, "voice")
        if not _STATE["body_niced"]:
            _STATE["body_niced"] = True
            priority.apply_self("body")          # after the first voice: it was started at the body's own priority
        logger.info(f"voice process {self._proc.pid} started (worker port {self.port})")
        self._emit("voice_process_start", pid=self._proc.pid, port=self.port)

    async def _read_status(self) -> None:
        r = await self.client._http().get(f"{self.client.base}/voice/status", headers=self.client.headers(),
                                          timeout=1.0)
        if r.status_code == 200:
            self.status = r.json()
            wid = str(self.status.get("worker_id") or "")
            self.id = wid or "unregistered"
            self._connecting = not wid

    async def run(self, *, devmode: bool = False) -> None:
        await self._spawn()
        self._closed = False
        self._connecting = True
        proc = self._proc
        waiter = asyncio.ensure_future(proc.wait())
        try:
            while not waiter.done():
                try:
                    await self._read_status()
                except Exception as _swallowed:  # noqa: BLE001 — not up yet, or busy: the next reading says
                    logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
                    pass
                await asyncio.wait({waiter}, timeout=self.status_s)
        finally:
            if not waiter.done():
                waiter.cancel()
            self._closed = True
            self.id = "unregistered"
            code = proc.returncode
            self._emit("voice_process_exit", pid=proc.pid, code=code)
            logger.warning(f"voice process {proc.pid} ended (code {code})")

    async def aclose(self) -> None:
        """End the voice process: SIGTERM, then SIGKILL after `stop_s`. Idempotent."""
        self._closed = True
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=self.stop_s)
        except asyncio.TimeoutError:
            logger.warning(f"voice process {proc.pid} did not stop in {self.stop_s:g}s — killing it")
            proc.kill()
            await proc.wait()
        except ProcessLookupError as _swallowed:
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass
        await self.client.aclose()

    def _emit(self, step: str, **extra) -> None:
        try:
            from voice import observer
            observer.emit("homeostasis", step, extra={"cat": "voice", "kind_diag": step, **extra})
        except Exception as _swallowed:  # noqa: BLE001
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass


def make_child() -> VoiceChild:
    return VoiceChild()


def factory():
    """What builds the voice worker for this deployment: the embedded `AgentServer`, or the voice's own process."""
    if embedded():
        from voice.engine.pipeline.agent import make_server
        return make_server
    return make_child

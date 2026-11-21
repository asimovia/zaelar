"""LiveKit Agents worker — what the voice's own process (`child.py`, `python -m voice.engine`) builds its session with.

`make_server(entry)` returns the ``AgentServer`` the voice process runs around its session (`child_session.entrypoint`),
with the worker's health port, the room filter and the mediated LiveKit credential; the session reads the endpointing,
the start options, what must exist before the room connects and the warm TTS from here. The module is also the
namespace `agent_events` reads its pipeline handlers through (`_ag.<name>`), so a patch here still governs them. The
embedded session (the voice as a thread of the body, with the old turn's voice node) is gone (INI-078 F2).
"""
from __future__ import annotations

import logging
import os

from livekit.agents import (
    AgentServer,
    JobExecutorType,
    JobRequest,
)

from ..core.config import SETTINGS
from ..core.logging import setup_console_logging
from ..speech.tts import start_prewarm
from .first_air import FirstAir, decide_kickoff, greeting_prompt, kickoff_recent, mark_kickoff, silent_first_run  # noqa: F401
from .prewarm import prewarm  # noqa: E402,F401 — V2-778 F1: moved, imported back under its name

logger = logging.getLogger("zaelar.agent")


# GUARD: one kickoff per room (V2-047 F8) — moved to `first_air.py` with V2-745, re-exported under the
# historical private names so every call site and test here reads unchanged.
_kickoff_recent, _mark_kickoff = kickoff_recent, mark_kickoff


def _endpointing_opts(flux: bool | None = None) -> dict:
    """How much silence closes a turn. The values live in `voice/endpointing.py` — the SINGLE source of truth for
    this decision, written from real sessions and orphaned until now. Env overrides allow hot adjustment
    without touching code, and WIN: with either `ZAELAR_ENDPOINT_*_S` set it is the dynamic mode with those bounds.
    With the Flux ear (`flux` None = read it) and no override it is FIXED at `stt_flux_min_delay`: Flux already
    decided the turn ended, and LiveKit's dynamic average (built for VAD endpointing) took a long pause after a
    sentence with no transcript as a pause INSIDE a turn — measured on a cloud Machine 2026-11-19, every later turn
    then waited the 3 s ceiling (`eou=3.00s`) for the rest of the session."""
    from voice import endpointing as _ep
    if flux is None:
        try:
            from ..speech.stt import deepgram as _dg
            flux = _dg.flux_active()
        except Exception as e:  # noqa: BLE001 — unreadable ear: the dynamic endpointing, as before
            logger.debug("endpointing: flux unreadable — %r", e)
            flux = False
    if flux and not any((os.getenv(k) or "").strip() for k in ("ZAELAR_ENDPOINT_MIN_S", "ZAELAR_ENDPOINT_MAX_S")):
        return {"mode": "fixed", "min_delay": SETTINGS.stt_flux_min_delay, "max_delay": SETTINGS.stt_flux_min_delay}

    def _f(name: str, default: float) -> float:
        v = (os.getenv(name) or "").strip()
        try:
            return float(v) if v else default
        except ValueError:
            return default

    lo = _f("ZAELAR_ENDPOINT_MIN_S", _ep.HOLD_BASE)
    hi = _f("ZAELAR_ENDPOINT_MAX_S", _ep.HOLD_MAX)
    return {"mode": "dynamic", "min_delay": lo, "max_delay": max(lo, hi)}


def _session_start_opts() -> dict:
    """Extra `AgentSession.start` options. A MEDIATED instance holds no LiveKit key (see `make_server`), and the SDK
    uploads a session's recording, traces and logs to the provider's observability endpoint signed with that key:
    every session would end in a 401 and an ERROR. So it does not record. Elsewhere the SDK default stands.
    Voice isolation (V2-812 T-08) adds `room_options` only when the setting is on AND the transport serves it."""
    from nucleo.energy import egress as llm_egress
    from .voice_isolation import room_options
    opts = {"record": False} if llm_egress.mediated() else {}
    return {**opts, **room_options(SETTINGS.voice_isolation, SETTINGS.livekit_url)}


def _before_connect() -> None:
    """What has to exist before the room connects. Voice isolation (V2-812 T-08): the plugin must be registered
    BEFORE the connection, or the FFI never initialises it for it and the filter fails with code 209. Fails open."""
    setup_console_logging()
    from . import thread_qos
    thread_qos.interactive()                   # V2-887: this is the voice job's thread; ask the OS to serve it first
    from .voice_isolation import preload as _preload_isolation
    _preload_isolation(SETTINGS.voice_isolation, SETTINGS.livekit_url)


def _warm_tts(ctx) -> None:
    """Open the warm TTS's connection on THIS loop, before the room connects: the handshake overlaps the connect
    instead of the greeting (`setup_fnc` runs with no loop, so it cannot)."""
    ud = getattr(getattr(ctx, "proc", None), "userdata", None) or {}
    start_prewarm(ud.get("tts"))


async def request_fnc(req: JobRequest) -> None:
    """Only take our own rooms (several engines/projects can share one LiveKit server; tokens mint
    ``<room_name>-<uuid>``, server/livekit_api.py). A foreign room is PASSED ON, never terminated: a bare
    ``reject()`` means ``terminate=True``, and with one-worker-at-a-time dispatch the owner is then never asked."""
    from voice.engine.core.config import accepts_room
    if accepts_room(SETTINGS.room_name, req.room.name):
        await req.accept()
    else:
        await req.reject(terminate=False)


def worker_health_port() -> int:
    """The voice worker's health port: the app port + 1000 (43917 → 44917), so every instance — and every second
    instance on another app port — lands on a fixed, predictable port. `ZAELAR_WORKER_PORT` overrides it."""
    explicit = (os.getenv("ZAELAR_WORKER_PORT") or "").strip()
    if explicit:
        return int(explicit)
    return int((os.getenv("PORT") or "43917").strip()) + 1000


def make_server(entry) -> AgentServer:
    """Build the voice process's ``AgentServer`` around its session `entry` (`child_session.entrypoint`).

    VERIFIED empirically against livekit-agents 1.6.4 (voice-lab-2 .venv):
      * ``AgentServer.__init__`` does NOT take ``entrypoint_fnc``/``prewarm_fnc`` —
        those parameters live on the legacy ``WorkerOptions``. In 1.6.4 the
        entrypoint is registered via the ``rtc_session`` decorator/registrar
        (``server.rtc_session(entrypoint)``) and prewarm is the ``setup_fnc``
        constructor argument. (``cli.run_app`` accepts either an ``AgentServer`` or
        a ``WorkerOptions``; ``_legacy.run_app`` converts WorkerOptions ->
        ``AgentServer.from_server_options``.)
      * ``JobExecutorType.THREAD`` runs the job in a thread of the current process
        (vs. the default ``PROCESS`` that spawns a subprocess), which is what lets
        the voice job share state with the zaelar brain.

    Signatures observed:
      AgentServer.__init__(self, *, job_executor_type=PROCESS, ..., setup_fnc=None,
                           load_fnc=None, ws_url=None, api_key=None, api_secret=None, ...)
      AgentServer.rtc_session(self, func=None, *, agent_name="", type=ROOM, ...)
    """
    # MEDIATED: the worker registers THROUGH egress, which holds the LiveKit secret. The SDK signs its own JWT with
    # whatever key it is given, so it is given this instance's egress credential: egress reads who it is from the
    # token's `iss`, signs the real registration and lets it through only under this instance's own agent name.
    from nucleo.energy import egress as llm_egress
    lk_url, lk_key, lk_secret = SETTINGS.livekit_url, SETTINGS.livekit_api_key, SETTINGS.livekit_api_secret
    if llm_egress.mediated():
        lk_url = llm_egress.root().replace("https://", "wss://", 1) + "/livekit"
        lk_key = lk_secret = llm_egress.credential()
    server = AgentServer(
        job_executor_type=JobExecutorType.THREAD,
        setup_fnc=prewarm,                      # prewarm is `setup_fnc` on AgentServer
        # Keep one fully-warm executor idle (prewarm loads Whisper) so the first
        # connect joins fast; the ProcPool warms it for the THREAD executor too.
        num_idle_processes=1,
        initialize_process_timeout=90,          # prewarm loads Whisper (+ Ollama on local)
        ws_url=lk_url,
        api_key=lk_key,
        api_secret=lk_secret,
        # FIXED PORT, THIS MACHINE ONLY (2026-10-21). The worker opens a small health server (`/`, `/worker`); in
        # dev mode LiveKit's default is port 0 on every interface — a NEW random port at each start, reachable
        # from the local network, and impossible for `stop` to name, so a dead instance's port went unnoticed.
        # The engine always starts on the same ports: see `worker_health_port()` and `scripts/zaelar.py::PORTS`.
        host="127.0.0.1",
        port=worker_health_port(),
    )
    # on_request = request_fnc: only service zaelar's own rooms (room isolation when
    # a local LiveKit dev server is shared with other projects, e.g. voice-lab-2).
    from voice.engine.core.config import dispatch_agent_name
    # `entry`: the voice's OWN process passes its session (`child_session.entrypoint`, V2-891) — the only voice there is.
    server.rtc_session(entry, on_request=request_fnc, agent_name=dispatch_agent_name())
    return server




"""child.py — the voice in its own process: `python -m voice.engine` (V2-891).

WHY A PROCESS. Embedded, the LiveKit job is a THREAD of the body (`JobExecutorType.THREAD`): the VAD, the ear's
websocket and the mouth share one interpreter, one GIL and one heap with the memory, the widgets, the listeners and
the browser bridge. On a host short of memory the body's pages are the ones the OS compresses and swaps, and every
time the voice thread touches the shared heap (a GC pass, an import, an allocation) it waits for them: the ear stops
(«job executor is unresponsive»), the ear's websocket times out (Deepgram 1011, the sentence arrives in pieces).
Here the voice holds only what it needs — LiveKit, the VAD, the ear and the mouth — so its working set stays small
and resident, and nothing the body does can stall its loop.

What runs here: the LiveKit `AgentServer` (THREAD executor, inside THIS process), the session of
`child_session.py`, the link to the body (`body_link.py`), and a few control routes on the worker's own health port
(`agent.worker_health_port()`, loopback only, the body's token required):

    POST /voice/say         speak a text (NDJSON: {"id"} at once, {"done"} once it has played)
    POST /voice/reply       a typed line becomes a turn (the screen that typed it travels with it)
    POST /voice/audio       {"output": bool} mute/unmute synthesis · {"input": bool} open/close the ear
    POST /voice/clear_turn  forget the user turn the body's gate discarded
    POST /voice/tts         re-point the live voice {"voice_id", "lang"}
    POST /voice/env         the body's live `ZAELAR_*` settings
    POST /voice/close       end the session {"reason"}
    GET  /voice/status      pid, RSS, sessions, whether a session is live

The process ends when its parent does: it watches its parent pid, so a body that dies never leaves a voice talking
to nobody. Started only by the body (`voice/child_process.py`) — never by hand in production.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time

from loguru import logger

from aiohttp import web

from . import body_link
from .child_session import LIVE

ROUTE_PREFIX = "/voice"


def _authorised(request) -> bool:
    want = os.getenv(body_link.TOKEN_ENV) or ""
    return bool(want) and request.headers.get(body_link.HEADER, "") == want


def rss_mb() -> float:
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 2 ** 20, 1)
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return 0.0


async def _on_session_loop(coro_fn):
    """Run `coro_fn()` on the live session's loop (the THREAD executor's), from the control server's loop."""
    from .child_session import LIVE
    loop = LIVE.get("loop")
    if loop is None or loop.is_closed():
        raise LookupError("no live session")
    try:
        here = asyncio.get_running_loop()
    except RuntimeError:
        here = None
    if here is loop:
        return await coro_fn()
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro_fn(), loop))


def _deny():
    return web.json_response({"ok": False, "error": "forbidden"}, status=403)


async def _json(request) -> dict:
    try:
        return await request.json()
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return {}


async def say(request):
    if not _authorised(request):
        return _deny()
    body = await _json(request)
    from .remote_brain import apply_env
    apply_env(body.get("env"))
    text = str(body.get("text") or "").strip()
    resp = web.StreamResponse(headers={"content-type": "application/x-ndjson"})
    await resp.prepare(request)
    if not text or LIVE.get("session") is None:
        await resp.write(json.dumps({"id": "", "done": True, "error": "no_session"}).encode() + b"\n")
        return resp
    alias, t0 = str(body.get("alias") or ""), time.perf_counter()
    got: dict = {}

    async def _do():
        session = LIVE["session"]
        handle = session.say(text, allow_interruptions=bool(body.get("allow_interruptions", True)),
                             add_to_chat_ctx=not bool(body.get("ephemeral")))
        if alias:
            LIVE["aliases"][str(getattr(handle, "id", ""))] = alias
        got["id"] = str(getattr(handle, "id", ""))
        return handle

    try:
        handle = await _on_session_loop(_do)
        await resp.write(json.dumps({"id": got.get("id", "")}).encode() + b"\n")

        async def _wait():
            await handle
        await _on_session_loop(_wait)
        await resp.write(json.dumps({"done": True, "interrupted": bool(getattr(handle, "interrupted", False)),
                                     "playout_ms": round((time.perf_counter() - t0) * 1000)}).encode() + b"\n")
    except Exception as e:  # noqa: BLE001
        await resp.write(json.dumps({"done": True, "error": repr(e)[:200]}).encode() + b"\n")
    return resp


async def reply(request):
    if not _authorised(request):
        return _deny()
    body = await _json(request)
    from .remote_brain import CHILD_ORIGIN, apply_env
    apply_env(body.get("env"))
    text = str(body.get("text") or "").strip()
    if not text or LIVE.get("session") is None:
        return web.json_response({"ok": False, "error": "no_session"})

    async def _do():
        tok = CHILD_ORIGIN.set(str(body.get("origin") or ""))
        try:
            if body.get("cut"):                # a typed line: the speech in course stops first, as a barge-in
                from .agent_events import cut_current_speech
                try:
                    cut_current_speech(LIVE["session"])
                except Exception as e:  # noqa: BLE001 — a cut that fails never drops his line
                    logger.warning(f"typed line: the speech in course was not cut — {e!r}")
            LIVE["session"].generate_reply(user_input=text,
                                           allow_interruptions=bool(body.get("allow_interruptions", True)))
        finally:
            CHILD_ORIGIN.reset(tok)
    await _on_session_loop(_do)
    return web.json_response({"ok": True})


async def audio(request):
    if not _authorised(request):
        return _deny()
    body = await _json(request)
    if LIVE.get("session") is None:
        return web.json_response({"ok": False, "error": "no_session"})

    async def _do():
        s = LIVE["session"]
        if "output" in body:
            s.output.set_audio_enabled(bool(body["output"]))
        if "input" in body:                    # the ear's whole effect, as in the embedded session
            from .agent_events import set_ear
            set_ear(s, bool(body["input"]))
    await _on_session_loop(_do)
    return web.json_response({"ok": True})


async def clear_turn(request):
    if not _authorised(request):
        return _deny()
    if LIVE.get("session") is None:
        return web.json_response({"ok": False, "error": "no_session"})

    async def _do():
        LIVE["session"].clear_user_turn()
    await _on_session_loop(_do)
    return web.json_response({"ok": True})


async def tts(request):
    if not _authorised(request):
        return _deny()
    body = await _json(request)
    from ..speech import live_tts
    took = live_tts.apply_voice(str(body.get("voice_id") or ""), body.get("lang") or None)
    return web.json_response({"ok": True, "took": bool(took)})


async def env(request):
    if not _authorised(request):
        return _deny()
    from .remote_brain import apply_env
    return web.json_response({"ok": True, "moved": apply_env((await _json(request)).get("env"))})


async def close(request):
    if not _authorised(request):
        return _deny()
    body = await _json(request)
    ctx = LIVE.get("ctx")
    if ctx is None:
        return web.json_response({"ok": False, "error": "no_session"})
    ctx.shutdown(reason=str(body.get("reason") or "body"))
    return web.json_response({"ok": True})


async def status(request):
    if not _authorised(request):
        return _deny()
    link = body_link.get()
    return web.json_response({"ok": True, "pid": os.getpid(), "rss_mb": rss_mb(), "nice": _nice(),
                              "live": LIVE.get("session") is not None, "room": LIVE.get("room", ""),
                              "sessions": LIVE.get("sessions", 0), "link": dict(link.stats),
                              "worker_id": _SERVER.get("id", "")})


def routes():
    """The aiohttp routes this process adds to the LiveKit worker's health server."""
    p = ROUTE_PREFIX
    return [web.post(f"{p}/say", say), web.post(f"{p}/reply", reply), web.post(f"{p}/audio", audio),
            web.post(f"{p}/clear_turn", clear_turn), web.post(f"{p}/tts", tts), web.post(f"{p}/env", env),
            web.post(f"{p}/close", close), web.get(f"{p}/status", status)]


def _nice() -> int | None:
    try:
        return os.getpriority(os.PRIO_PROCESS, 0)
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return None


_SERVER: dict = {"id": ""}


def install_routes(port: int) -> None:
    """Add the control routes to the LiveKit health server of THIS process (the one bound to `port`). LiveKit builds
    that server inside `AgentServer.run()`, so the routes are added the moment it starts, before it serves."""
    from livekit.agents.utils import http_server as _hs
    if getattr(_hs.HttpServer.start, "_zaelar_voice", False):
        return
    original = _hs.HttpServer.start

    async def start(self):
        if int(getattr(self, "_port", -1)) == int(port) and not getattr(self, "_zaelar_routes", False):
            self._app.add_routes(routes())
            self._zaelar_routes = True
        return await original(self)

    start._zaelar_voice = True
    _hs.HttpServer.start = start


def _forward_observer(link: body_link.BodyLink) -> None:
    from voice import observer_link
    observer_link.forward_to(lambda ev: link.send({"k": "emit", **ev}))


def _forward_lag(link: body_link.BodyLink) -> None:
    """The voice measures its own loop and the SDK's audio delays HERE; the body reads them (`voice/lag.note`), because
    the body holds the envelope the reading sheds."""
    from voice import lag
    lag.route_to(lambda lag_s, source: link.send({"k": "lag", "lag_s": float(lag_s), "source": str(source)}))


async def _watch_parent(server, parent: int, period_s: float = 1.0) -> None:
    while True:
        await asyncio.sleep(period_s)
        if os.getppid() != parent:
            logger.warning("voice process: the body is gone — closing")
            await server.aclose()
            return


async def _serve(server, devmode: bool) -> None:
    link = body_link.get()
    link.start()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: loop.create_task(server.aclose()))
        except (NotImplementedError, RuntimeError) as _swallowed:
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass
    watch = loop.create_task(_watch_parent(server, int(os.getenv("ZAELAR_VOICE_PARENT") or os.getppid())))

    async def _note_id():
        while True:
            _SERVER["id"] = str(getattr(server, "id", "") or "")
            await asyncio.sleep(0.5)
    ids = loop.create_task(_note_id())
    try:
        await server.run(devmode=devmode)
    finally:
        watch.cancel()
        ids.cancel()
        await link.aclose()


def main() -> None:
    os.environ["ZAELAR_VOICE_ROLE"] = "child"
    from ..core.logging import setup_console_logging
    setup_console_logging()
    import logging
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)   # the body reads /voice/status twice a second
    from nucleo.pulse import priority
    priority.apply_self("voice")                 # nice 0 + the lowest OOM score its privileges allow
    link = body_link.get()
    _forward_observer(link)
    _forward_lag(link)
    from nucleo.pulse import homeostasis
    homeostasis.watch_into(lambda at: link.send({"k": "lk_mark", "at": at}))   # the SDK's degraded marks → the body
    from . import agent as _ag
    from .child_session import entrypoint
    install_routes(_ag.worker_health_port())
    server = _ag.make_server(entry=entrypoint)
    devmode = os.getenv("ZAELAR_ENV", "dev").lower() != "prod"
    logger.info(f"voice process {os.getpid()} up — body {link.base}, worker port {_ag.worker_health_port()}")
    asyncio.run(_serve(server, devmode))

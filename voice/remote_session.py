"""voice/remote_session.py — the body's side of a voice that runs in its own process (V2-891).

The voice process (`python -m voice.engine`) observes; the body decides. Everything the session used to write into
this process's modules — `_busy` (who is speaking), the wake-word window, the typed-order marks, the trace of a
speech, the transcript on the wall — is replayed here from the events the voice process sends
(`POST /api/voice/child/events`), through the SAME handlers the embedded session registers (`agent_events.*`), handed
a session that answers over HTTP (`RemoteSession`). So every rule those handlers carry holds unchanged, in one copy.

What the body asks of the voice — speak (`voice/proactive`), turn a typed line into a turn (`voice/screens`), open or
close the ear (`voice/mic_input`), forget a discarded turn, re-point the voice (`speech/live_tts`), close the session
(the account's energy cap) — goes to the voice process's control routes (`voice/engine/pipeline/child.py`).

And the turn: `turn_lines(payload)` runs the voice provider (`NucleoLLM`, one per voice session, its state across
turns as embedded) inside the lead-in cover (`filler_audio.llm_node_with_filler`) and yields the NDJSON lines the
voice process reads (`remote_brain.remote_llm_node`).

The process boundary is a loopback socket with a per-spawn token; nothing here is reachable from outside.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
import uuid
from types import SimpleNamespace

from loguru import logger

#: The env this process gave the voice process at spawn names it (`ZAELAR_VOICE_*`, its body and worker addresses):
#: those are the voice's own and are never pushed as «settings».
_OWN_PREFIXES = ("ZAELAR_VOICE_", "ZAELAR_BODY_", "ZAELAR_WORKER_")


class ChildClient:
    """Body → voice process. Async calls from the body's loop; `post_soon` from anywhere (also the synchronous
    callers: re-pointing the live voice from a settings save never blocks on the voice process)."""

    def __init__(self, base: str, token: str) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self._client = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._env_sent: dict = {}
        self.stats = {"calls": 0, "failed": 0}

    def headers(self) -> dict:
        from voice.engine.pipeline import body_link
        return {body_link.HEADER: self.token}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _http(self):
        import httpx
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0))
        return self._client

    def env_diff(self) -> dict:
        """The `ZAELAR_*` settings that changed since the last push (the language he picked, a mode)."""
        now = {k: v for k, v in os.environ.items() if k.startswith("ZAELAR_") and not k.startswith(_OWN_PREFIXES)}
        out = {k: v for k, v in now.items() if self._env_sent.get(k) != v}
        out.update({k: "" for k in self._env_sent if k not in now})
        self._env_sent = now
        return out

    def mark_env_sent(self, env: dict) -> None:
        self._env_sent = {k: v for k, v in env.items() if k.startswith("ZAELAR_") and not k.startswith(_OWN_PREFIXES)}

    async def post(self, path: str, payload: dict | None = None, timeout_s: float = 3.0) -> dict:
        self.stats["calls"] += 1
        try:
            r = await self._http().post(self.base + path, json=payload or {}, headers=self.headers(),
                                        timeout=timeout_s)
            return r.json() if r.status_code < 300 else {"ok": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:  # noqa: BLE001
            self.stats["failed"] += 1
            logger.warning(f"body→voice {path}: {e!r}")
            return {"ok": False, "error": repr(e)[:200]}

    def post_soon(self, path: str, payload: dict | None = None) -> None:
        """Fire and forget, from the body's loop or any thread."""
        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None and (loop is None or running is loop):
            running.create_task(self.post(path, payload))
        elif loop is not None and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.post(path, payload), loop)

    async def say_stream(self, payload: dict):
        """`/voice/say` as it plays: the speech id at once, then `done` when it has sounded."""
        async with self._http().stream("POST", self.base + "/voice/say", json=payload, headers=self.headers(),
                                       timeout=None) as r:
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as _swallowed:  # noqa: BLE001
                logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
                pass
            self._client = None


class RemoteSpeech:
    """A speech the voice process is playing for the body — awaitable like LiveKit's `SpeechHandle`. Its `id` is the
    body's own alias: the voice process names it back in every event about that speech."""

    def __init__(self, alias: str) -> None:
        self.id = alias
        self.lk_id = ""
        self.interrupted = False
        self._done = asyncio.get_running_loop().create_future()

    def done(self) -> bool:
        return self._done.done()

    def _finish(self, info: dict | None = None) -> None:
        self.interrupted = bool((info or {}).get("interrupted"))
        if not self._done.done():
            self._done.set_result(info or {})

    def __await__(self):
        return self._done.__await__()


class _Audio:
    def __init__(self, client: ChildClient, key: str) -> None:
        self._client, self._key = client, key

    def set_audio_enabled(self, enabled: bool) -> None:
        self._client.post_soon("/voice/audio", {self._key: bool(enabled)})


class RemoteSession:
    """The slice of LiveKit's `AgentSession` the session handlers use, answered by the voice process."""

    def __init__(self, client: ChildClient) -> None:
        self.client = client
        self.output = _Audio(client, "output")
        self.input = _Audio(client, "input")
        self._close_cbs: list = []

    def say(self, text: str, allow_interruptions: bool = True, add_to_chat_ctx: bool = True) -> RemoteSpeech:
        handle = RemoteSpeech("rs_" + uuid.uuid4().hex[:12])
        payload = {"text": text, "allow_interruptions": allow_interruptions, "ephemeral": not add_to_chat_ctx,
                   "alias": handle.id, "env": self.client.env_diff()}

        async def _play():
            try:
                async for line in self.client.say_stream(payload):
                    if line.get("id"):
                        handle.lk_id = str(line["id"])
                    if line.get("done"):
                        handle._finish(line)
                        return
            except Exception as e:  # noqa: BLE001
                logger.warning(f"body→voice say: {e!r}")
            handle._finish({"error": "lost"})
        asyncio.get_running_loop().create_task(_play())
        return handle

    def generate_reply(self, user_input: str = "", allow_interruptions: bool = True, **_kw) -> None:
        from voice import screens
        self.client.post_soon("/voice/reply", {"text": user_input, "origin": screens.ORIGIN.get(),
                                               "allow_interruptions": allow_interruptions,
                                               "env": self.client.env_diff()})

    def clear_user_turn(self) -> None:
        self.client.post_soon("/voice/clear_turn", {})

    def on(self, event: str, cb=None):
        if event == "close" and cb is not None:
            self._close_cbs.append(cb)
        return cb

    def fire_close(self, ev=None) -> None:
        for cb in list(self._close_cbs):
            try:
                cb(ev)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"remote session close callback: {e!r}")
        self._close_cbs.clear()


class RemoteTTS:
    """What `live_tts` holds in the body: re-pointing it re-points the voice process's live TTS. Fire and forget — the
    settings save never waits on the voice; the voice process logs a voice it could not take, and the persisted
    setting applies on its next session either way (the pre-V2-733 behaviour)."""

    def __init__(self, client: ChildClient) -> None:
        self._client = client

    def update_options(self, voice_id: str | None = None, language: str | None = None) -> None:
        self._client.post_soon("/voice/tts", {"voice_id": voice_id or "", "lang": language or ""})


class _SpeechRef:
    """The LiveKit speech a remote turn's reply belongs to, as `_SpeechHandleContextVar` holds it embedded."""

    def __init__(self, sid: str) -> None:
        self.id = sid
        self._done = False

    def done(self) -> bool:
        return self._done

    def finish(self) -> None:
        self._done = True


class _NoAir:
    def on_speaking(self) -> None:          # the first-air veil lives with the room, in the voice process
        return None


class _NoSM:
    def on_user_state(self, _s) -> None:    # the derived state machine lives in the voice process
        return None


class _NoBoot:
    def close(self) -> None:
        return None


# ── the mirror of the live session ──────────────────────────────────────────────────────────────────────────────

_M: dict = dict(client=None, session=None, brain=None, busy=dict(bot=False, user=False),
               onset=dict(voice_ended=0.0), wake=dict(last_user_final=0.0, spot_at=0.0), typed=None,
               speak=None, closer=None, id_token=None, room="", tts=None, events=0)
#: room → the handles its session registered (several may overlap for an instant while the voice moves screens)
_ROOMS: dict = {}
_ONSET_MAX_S = 30.0
_lock = threading.Lock()


def use_client(client: ChildClient | None) -> None:
    _M["client"] = client


def client() -> ChildClient | None:
    return _M["client"]


def live() -> bool:
    return _M["session"] is not None


def _emit(*a, **k):
    """The observer's own `emit`, called through `_obs()` where the stack decides the piece (see `_obs`)."""
    return _obs()(*a, **k)


def _obs():
    """The observer's `emit` itself — handed to the replayed handlers so the event's piece is read from THEIR module
    (`observability/pieces.emitter` walks up from `emit`'s caller): a wrapper here would stamp this relay instead."""
    from voice.observer import emit
    return emit


async def _direct(coro_fn) -> None:
    """The body's `_on_session_loop`: the remote session's calls are made from the body's own loop."""
    await coro_fn()


def _brain():
    if _M["brain"] is None:
        from voice.engine.core.config import SETTINGS
        from voice.engine.llm import build_llm
        _M["brain"] = build_llm(SETTINGS.llm_provider, SETTINGS.llm_model)
    return _M["brain"]


def _started(ev: dict) -> None:
    from voice import attention, proactive, screens
    from voice.engine.pipeline import agent_events as _ae
    from voice.engine.pipeline.session_health import on_session_alive
    from voice.engine.core.config import SETTINGS
    room = str(ev.get("room") or "")
    if room in _ROOMS:                          # the same room dispatched again: the old one is gone
        _closed({"cause": "replaced", "room": room})
    cl = _M["client"]
    cl.bind(asyncio.get_running_loop())
    remote = RemoteSession(cl)
    # Another room may still be closing (the voice moving between screens): its handles stay in `_ROOMS` and its own
    # close clears only what is still its own, exactly as the embedded sessions do.
    _M.update(session=remote, room=room, brain=None)
    _M["busy"].update(bot=False, user=False)
    _brain()
    try:
        attention.reset()
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        pass
    if SETTINGS.llm_provider == "nucleo":
        async def _prime():
            try:
                from nucleo.flash import memory_cache
                await memory_cache.prime()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"nucleo memory-cache prime skipped (voice continues): {e}")
        asyncio.get_running_loop().create_task(_prime())
    busy = _M["busy"]

    async def _speak(text: str) -> None:
        return await _ae._speak(text, _busy=busy, _emit=_obs(), _on_session_loop=_direct, session=remote)

    async def _speak_ephemeral(text: str) -> None:
        await remote.say((text or "").strip(), allow_interruptions=True, add_to_chat_ctx=False)

    _M["speak"] = _speak
    proactive.register_speaker(_speak)          # its loop's lag is measured where it runs: the voice process
    proactive.register_ephemeral_speaker(_speak_ephemeral)
    proactive.register_busy_probe(lambda: busy["bot"] or busy["user"])
    proactive.register_user_probe(lambda: bool(busy["user"]))
    proactive.register_bot_probe(lambda: bool(busy["bot"]))
    from nucleo.energy import account as _cloud_account, limits as _account_limits

    async def _close_account_session(reason: str) -> None:
        _emit("session", f"account energy exhausted ({reason}) — closing", role="system")
        if _line := _account_limits.spoken_line(reason):
            try:
                await remote.say(_line, allow_interruptions=True)
            except Exception as _swallowed:  # noqa: BLE001
                logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
                pass
        for _ in range(50):
            if not busy["bot"]:
                break
            await asyncio.sleep(0.2)
        await asyncio.sleep(0.3)
        await cl.post("/voice/close", {"reason": f"account:{reason}"})

    _M["closer"] = _close_account_session
    if _cloud_account.is_cloud_account():
        _account_limits.register_closer(_close_account_session)
    typed = _ae.open_typed_door(_emit=_obs(), _on_session_loop=_direct, session=remote)
    _M["typed"] = typed
    _ae.open_mic_door(session=remote, _emit=_obs())
    screens.register_typed(typed)
    on_session_alive()
    try:
        from observability import identity
        _M["id_token"] = identity.voice_connected()
    except Exception:  # noqa: BLE001
        _M["id_token"] = None
    try:
        from voice.engine.speech import live_tts
        _M["tts"] = RemoteTTS(cl)
        live_tts.attach(_M["tts"], str(ev.get("tts") or SETTINGS.tts_provider))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"remote live_tts not attached: {e!r}")
    _ROOMS[room] = dict(session=_M["session"], typed=_M["typed"], speak=_M["speak"], closer=_M["closer"],
                        id_token=_M["id_token"], tts=_M["tts"])


def _transport_down(ev: dict | None = None) -> None:
    room = str((ev or {}).get("room") or _M["room"])
    h = _ROOMS.get(room)
    if h is None:
        return
    tok, h["id_token"] = h.get("id_token"), None
    if room == _M["room"]:
        _M["id_token"] = None
    if tok is not None:
        try:
            from observability import identity
            identity.voice_disconnected(tok)
        except Exception as _swallowed:  # noqa: BLE001
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass


def _closed(ev: dict) -> None:
    room = str(ev.get("room") or _M["room"])
    h = _ROOMS.get(room)
    if h is None:
        return
    from voice import proactive
    from voice.engine.pipeline import agent_events as _ae
    from nucleo.energy import limits as _account_limits
    err = str(ev.get("error") or "") or None
    _ae._on_close(SimpleNamespace(reason=str(ev.get("cause") or ""), error=err), _account_limits=_account_limits,
                  _close_account_session=h["closer"], _emit=_obs(), _proactive=proactive, _speak=h["speak"],
                  boot=_NoBoot(), _typed=h["typed"])
    h["session"].fire_close(ev)
    _transport_down({"room": room})
    try:
        from voice.engine.speech import live_tts
        live_tts.detach(h["tts"])               # only if it is still the attached one
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        pass
    _ROOMS.pop(room, None)
    if room == _M["room"]:
        _M.update(session=None, typed=None, speak=None, closer=None, tts=None, id_token=None)
        _M["busy"].update(bot=False, user=False)


def _metric(ev: dict):
    cls = type(str(ev.get("type") or "Metrics"), (), {})
    m = cls()
    for k, v in ev.items():
        if k not in ("k", "type", "at"):
            setattr(m, k, v)
    return SimpleNamespace(metrics=m)


def handle(ev: dict) -> None:
    """One event from the voice process, replayed through the handler the embedded session runs for it."""
    from voice.engine.pipeline import agent_events as _ae
    k = ev.get("k")
    _M["events"] += 1
    if k == "emit":
        extra = dict(ev.get("extra") or {})
        if ev.get("piece"):
            extra["piece"] = ev["piece"]
            if ev.get("piece_src"):
                extra["piece_src"] = ev["piece_src"]
        _emit(str(ev.get("kind") or ""), str(ev.get("label") or ""), text=str(ev.get("text") or ""),
              role=str(ev.get("role") or ""), extra=extra or None)
        return
    if k == "session":
        what = ev.get("what")
        if what == "started":
            _started(ev)
        elif what == "closed":
            _closed(ev)
        elif what == "transport_down":
            _transport_down(ev)
        return
    if k == "lag":
        from voice import lag
        lag.note(float(ev.get("lag_s") or 0), str(ev.get("source") or lag.LOOP))
        return
    if k == "lk_mark":
        from nucleo.pulse import homeostasis
        homeostasis.note_mark(ev.get("at"))
        return
    if k == "preflight":
        from voice.engine.pipeline import eager_brief
        eager_brief.on_preflight(str(ev.get("text") or ""))
        return
    remote = _M["session"]
    if remote is None:
        return                                  # a fact about a session the body never saw start
    if k == "state":
        _ae.on_state_change(SimpleNamespace(value=str(ev.get("state") or "")), _ONSET_MAX_S=_ONSET_MAX_S,
                            _STATE_TRACE_SAFE=_ae.STATE_TRACE_SAFE, _air=_NoAir(), _busy=_M["busy"], _emit=_obs(),
                            _onset=_M["onset"])
    elif k == "user_state":
        _ae._on_user_state(SimpleNamespace(new_state=str(ev.get("state") or "")), _busy=_M["busy"], _emit=_obs(),
                           _onset=_M["onset"], sm=_NoSM())
    elif k == "transcript":
        _ae._on_transcript(SimpleNamespace(is_final=bool(ev.get("final")), transcript=str(ev.get("text") or "")),
                           _emit=_obs(), _wake=_M["wake"])
    elif k == "item":
        _ae._on_item(SimpleNamespace(item=SimpleNamespace(role=ev.get("role"), text_content=ev.get("text"))),
                     _emit=_obs(), speech_id=str(ev.get("speech_id") or ""), surfaced=bool(ev.get("surfaced")))
    elif k == "false_interruption":
        _ae.on_false_interruption(bool(ev.get("resumed")), _emit=_obs())
    elif k == "overlap":
        _ae.on_overlap(bool(ev.get("is_interruption")), _emit=_obs())
    elif k == "metrics":
        from voice.engine.pipeline.metrics_tap import on_metrics
        on_metrics(_metric(ev), _obs())
    elif k == "data":
        try:
            raw = base64.b64decode(str(ev.get("data") or ""))
        except Exception as _swallowed:  # noqa: BLE001
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            return
        _ae._on_data(SimpleNamespace(topic=ev.get("topic"), data=raw), _emit=_obs(), _json=json, _wake=_M["wake"],
                     session=remote)


def handle_batch(events: list) -> int:
    n = 0
    for ev in events or ():
        try:
            handle(ev if isinstance(ev, dict) else {})
            n += 1
        except Exception as e:  # noqa: BLE001 — one bad event never drops the rest of the batch
            logger.warning(f"voice event {str((ev or {}).get('k'))!r} not replayed: {e!r}")
    return n


# ── the kickoff and the turn ────────────────────────────────────────────────────────────────────────────────────

def kickoff(room: str) -> dict:
    """The first-turn decision for a session the voice process just started: the instruction to greet, or none."""
    from voice.engine.pipeline import first_air
    text = first_air.decide_kickoff(room, _obs())
    cl = _M["client"]
    return {"greet": text, "env": cl.env_diff() if cl is not None else {}}


async def turn_lines(payload: dict):
    """One voice turn, as NDJSON lines: the voice provider inside the lead-in cover, exactly as embedded."""
    from livekit.agents.llm import ChatContext
    from livekit.agents.types import FlushSentinel
    from livekit.agents.voice.agent_activity import _SpeechHandleContextVar
    from voice import screens
    from voice.engine.speech import echo_cut, filler_audio as _fa
    cl = _M["client"]
    env = cl.env_diff() if cl is not None else {}
    if env:
        yield {"t": "env", "env": env}
    text = str(payload.get("text") or "")
    brain = _brain()
    ctx = ChatContext.empty()
    ctx.add_message(role="user", content=text)
    origin = str(payload.get("origin") or "")
    tok_o = screens.ORIGIN.set(origin) if origin else None
    ref = _SpeechRef(str(payload.get("speech_id") or ""))
    tok_s = _SpeechHandleContextVar.set(ref)

    async def _model(_agent, chat_ctx, _tools, _ms):
        async with brain.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                yield chunk

    held: str | None = None                      # a str chunk is the cover only if a FlushSentinel follows it
    try:
        async for chunk in _fa.llm_node_with_filler(None, _model, ctx, [], None):
            if isinstance(chunk, FlushSentinel):
                if held is not None:
                    phrase, held = held.strip(), None
                    _fa.strip_if_filler(phrase)  # the voice process strips it from ITS transcript; not here
                    yield {"t": "filler", "text": phrase}
                continue
            if held is not None:
                yield {"t": "c", "text": held}
                held = None
            if isinstance(chunk, str):
                held = chunk
                continue
            content = echo_cut.chunk_text(chunk)
            if content:
                yield {"t": "c", "text": content}
        if held is not None:
            yield {"t": "c", "text": held}
        yield {"t": "end"}
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — the voice process says «say again»; the cause stays here
        logger.warning(f"remote turn failed: {e!r}")
        yield {"t": "err", "msg": repr(e)[:200]}
    finally:
        ref.finish()
        try:
            _SpeechHandleContextVar.reset(tok_s)
            if tok_o is not None:
                screens.ORIGIN.reset(tok_o)
        except ValueError as _swallowed:                       # a generator closed from another context: the vars die with it
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass


def reset_for_tests() -> None:
    _ROOMS.clear()
    _M.update(client=None, session=None, brain=None, typed=None, speak=None, closer=None, id_token=None, room="",
              tts=None, events=0)
    _M["busy"].update(bot=False, user=False)
    _M["onset"]["voice_ended"] = 0.0
    _M["wake"].update(last_user_final=0.0, spot_at=0.0)


def snapshot() -> dict:
    return {"live": live(), "room": _M["room"], "events": _M["events"], "busy": dict(_M["busy"]),
            "at": time.time()}

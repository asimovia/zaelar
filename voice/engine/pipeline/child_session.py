"""child_session.py — the voice session as it runs in its OWN process (V2-891).

The same `AgentSession` the embedded entrypoint (`agent.py::entrypoint`) builds — the same VAD, ear, mouth, turn
handling, barge-in tuning, preemptive generation, figures made speakable, lead-in segment, first-air veil — with
one difference: every fact the brain reads is HANDED to the body instead of written into this process's modules.

  · his VAD edges, transcripts, the agent's derived state, the conversation items, the room's data packets
    (PTT, the wake word, mute, the 🔊 toggle, typed lines), metrics, errors, the preflight end of turn and the
    session's open/close → `body_link.send(...)`, replayed by the body through the SAME handlers
    (`voice/remote_session.py` → `agent_events.*`) against a session that answers over HTTP;
  · the reply's text ← the body's turn stream (`remote_brain.remote_llm_node`);
  · what the body asks of this session (speak, reply to a typed line, mute, clear a discarded turn, re-point the
    voice, close) → the control routes of `child.py`, on this process's worker port.

What stays HERE because it is the room's: the boot channel (topic vl2) and the first-air veil, the mic recorder,
the reply-wall tee of what the mouth was fed, the speech-id aliases of what the body asked to say.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

from livekit.agents import AgentSession, JobContext

from . import body_link
from ..core.config import SETTINGS
from ..core.state import State, StateMachine

logger = logging.getLogger("zaelar.voice-process")

#: The live session of this process, for the control routes (`child.py`). One at a time.
LIVE: dict = dict(session=None, ctx=None, loop=None, aliases={}, room="", started=0.0, sessions=0)


def alias_of(speech_id: str) -> str:
    """The body's own name for a speech it asked for (`/voice/say`), else LiveKit's id."""
    sid = str(speech_id or "")
    return LIVE["aliases"].get(sid, sid)


def _metric_fields(m) -> dict:
    out = {"type": type(m).__name__}
    for attr in ("ttft", "duration", "ttfb", "end_of_utterance_delay", "audio_duration", "characters_count",
                 "speech_id"):
        v = getattr(m, attr, None)
        if isinstance(v, (int, float, str)):
            out[attr] = alias_of(v) if attr == "speech_id" else v
    fam = {"STTMetrics": "stt", "TTSMetrics": "tts"}.get(out["type"])
    if fam:   # V2-896 P1-1 — who produced it is known HERE (the adapter lives in this process); the body bills it
        from ..speech import relay
        out["provider"] = relay.provider_for(fam, m, getattr(SETTINGS, f"{fam}_provider"))
    return out


async def entrypoint(ctx: JobContext) -> None:
    from . import agent as _ag
    from .first_air import FirstAir
    from .instrument import BootChannel, tapped_vad
    from ..speech import build_stt, build_tts, build_turn_detection, build_vad
    from .remote_brain import RemoteBrainLLM
    from voice.observer import emit as _emit

    link = body_link.get()
    _ag._before_connect()
    _ag._warm_tts(ctx)                         # the TTS handshake overlaps the room connect, not the greeting
    await ctx.connect()
    session_id = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    boot = BootChannel(ctx.room, session_id)

    ud = ctx.proc.userdata
    vad_plain = ud.get("vad") or build_vad()
    stt = ud.get("stt") or build_stt(vad=vad_plain)
    tts = ud.get("tts") or build_tts()
    try:
        from ..speech import live_tts as _live_tts
        _live_tts.attach(tts, SETTINGS.tts_provider)
        _live_tts.apply_current()
    except Exception as e:  # noqa: BLE001
        logger.warning("live_tts: could not register the live TTS (%s)", e)
    turn_detection = build_turn_detection() or "vad"
    from ..speech.stt import deepgram as _dg_stt
    _flux = _dg_stt.flux_active()
    if _flux:
        turn_detection = "stt"
    vad_session = tapped_vad(vad_plain, boot) if boot.recording else vad_plain
    _endpointing = _ag._endpointing_opts()
    if _flux:
        _endpointing = {**_endpointing, "min_delay": SETTINGS.stt_flux_min_delay}
    from . import agent_events as _ae
    _interruption = _ae._int_kwargs()

    _emit("worker_start", "motor de voz arriba (proceso propio)", role="system",
          extra={"profile": SETTINGS.profile, "stt": SETTINGS.stt_provider, "llm_provider": "remote",
                 "tts": SETTINGS.tts_provider, "turn": SETTINGS.turn_provider, "process": "voice",
                 **{f"endpoint_{k}": v for k, v in _endpointing.items()}})

    session = AgentSession(vad=vad_session, stt=stt, llm=RemoteBrainLLM(), tts=tts, turn_handling={
        "turn_detection": turn_detection, "endpointing": _endpointing, "interruption": _interruption,
        "preemptive_generation": {"enabled": True}})
    try:
        from . import preemptive_tap as _ptap
        _ptap.install(_emit)
    except Exception as e:  # noqa: BLE001
        logger.warning("preemptive tap not installed (%s)", e)

    air = FirstAir(ready=boot.ready, emit=_emit)

    def _on_state(state: State) -> None:
        if state.value == "speaking":
            air.on_speaking()
        link.send({"k": "state", "state": state.value})

    sm = StateMachine(on_change=_on_state)

    _wire(session, ctx, link, sm, _emit, tts, boot)

    from .zaelar_agent import ChildAgent
    from ..core import langs
    agent = ChildAgent(instructions=SETTINGS.system_prompt + " " + langs.current_language().reply_directive)
    try:
        from voice import lag as _lag
        _lag.watch()                             # THIS loop is the voice's: its lag and the SDK's delays go to the body
    except Exception as e:  # noqa: BLE001
        logger.warning("lag watch not installed (%s)", e)
    LIVE.update(session=session, ctx=ctx, loop=asyncio.get_running_loop(), room=ctx.room.name,
                started=time.time(), sessions=LIVE["sessions"] + 1)
    await session.start(room=ctx.room, agent=agent, **_ag._session_start_opts())
    logger.info("Session started (voice process).")
    link.send({"k": "session", "what": "started", "room": ctx.room.name, "session_id": session_id,
               "stt": SETTINGS.stt_provider, "tts": SETTINGS.tts_provider})

    async def _down(*_a) -> None:
        link.send({"k": "session", "what": "transport_down", "room": ctx.room.name})
    ctx.add_shutdown_callback(_down)

    boot.boot("memoria")
    await asyncio.sleep(0.25)
    boot.boot("reflejo")
    await asyncio.sleep(0.25)
    air.arm_safety_net()

    # The kickoff is the BODY's decision (memory, the typed line waiting, a room greeted seconds ago): it answers
    # with the instruction to greet, or nothing. No answer → no greeting: a greeting built without the memory is the
    # «hello, what do you need?» in the middle of a conversation that the decision exists to prevent.
    ahead = await link.ahead()               # «session started» rides WITH the question: the body reads it first
    decision = await link.post("/api/voice/child/kickoff", {"room": ctx.room.name, "events": ahead}, timeout_s=8.0)
    if not decision:
        link.back(ahead)                     # the body never answered: the facts return to the front of the line
    from .remote_brain import apply_env
    apply_env(decision.get("env"))
    text = str(decision.get("greet") or "")
    if not text:
        air.lift()
        return
    greeting = session.generate_reply(user_input=text, allow_interruptions=False)
    air.park(greeting, on_air=air.lift)
    await greeting


def _wire(session, ctx, link, sm, _emit, tts, boot) -> None:
    """The session's and the room's events → the body (`body_link.send`), each one the fact the embedded handler of
    the same name reads (`agent_events.*` replays it there). What stays here is the room's own: the reply-wall tee on
    a dead synthesis, the speech-id aliases, the live-TTS handle, the boot channel."""
    from . import agent as _ag
    from . import agent_events as _ae
    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        sm.on_agent_state(ev.new_state)

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        sm.on_user_state(ev.new_state)
        link.send({"k": "user_state", "state": getattr(ev.new_state, "value", ev.new_state)})

    @session.on("user_input_transcribed")
    def _on_transcript(ev) -> None:
        link.send({"k": "transcript", "final": bool(ev.is_final), "text": ev.transcript})

    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        role, text = getattr(item, "role", None), getattr(item, "text_content", None)
        _h = _ae._speech_of_this_task()
        link.send({"k": "item", "role": role, "text": text, "speech_id": alias_of(getattr(_h, "id", "")),
                   "surfaced": bool(text) and _ag._reply_wall.already_surfaced(text)})

    @session.on("agent_false_interruption")
    def _on_false(ev) -> None:
        link.send({"k": "false_interruption", "resumed": bool(getattr(ev, "resumed", False))})

    @session.on("overlapping_speech")
    def _on_overlap(ev) -> None:
        link.send({"k": "overlap", "is_interruption": bool(getattr(ev, "is_interruption", False))})

    @session.on("metrics_collected")
    def _on_metrics(ev) -> None:
        link.send({"k": "metrics", **_metric_fields(ev.metrics)})

    @session.on("error")
    def _on_error(ev) -> None:
        _err = getattr(ev, "error", ev)
        _emit("error", "⚠️ " + str(_err)[:200], role="system")
        logger.error("session error: %s", _err)
        if _ag._reply_wall.is_tts_dead(_err):
            _ag._reply_wall.surface(_emit)

    @ctx.room.on("data_received")
    def _on_data(packet) -> None:
        topic = getattr(packet, "topic", None)
        try:
            raw = base64.b64encode(bytes(packet.data)).decode("ascii")
        except Exception as _swallowed:  # noqa: BLE001
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            return
        link.send({"k": "data", "topic": topic, "data": raw})

    @session.on("close")
    def _on_close(ev) -> None:
        err = getattr(ev, "error", None)
        _r = getattr(ev, "reason", None)
        link.send({"k": "session", "what": "closed", "room": ctx.room.name,
                   "cause": str(getattr(_r, "value", _r) or "")[:40], "error": str(err)[:300] if err else ""})
        if LIVE["session"] is session:
            LIVE.update(session=None, ctx=None, loop=None)
            LIVE["aliases"].clear()
        try:
            from ..speech import live_tts as _lt
            _lt.detach(tts)
        except Exception as _swallowed:  # noqa: BLE001
            logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
            pass
        boot.close()

"""remote_brain.py — in the voice process the brain is a stream over loopback HTTP (V2-891).

The voice process holds the room, the VAD, the ear and the mouth; the turn — memory, tools, the brief, the lead-in
cover, the supersede marks — runs in the BODY (`python -m server`), exactly the pipeline it runs embedded. The seam is
the LiveKit `llm_node`: the session asks it for the reply's text, and here it is read from `POST /api/turn/stream`
(NDJSON) instead of from an in-process `LLMStream`.

Line types the body sends (`server/voice_child_api.py` writes them):
  · `{"t": "c", "text": …}`      a chunk of the reply, spoken as LiveKit speaks any chunk;
  · `{"t": "filler", "text": …}` the lead-in or work cover the body's `filler_audio` decided — it becomes its OWN
                                 segment here (text + `FlushSentinel`), so it sounds while the model still thinks,
                                 and it is marked so the transcript node strips it (the same contract as embedded);
  · `{"t": "env", "env": {…}}`   the body's live `ZAELAR_*` settings (the language he just picked, a mode), applied
                                 to this process before the next sentence is synthesised;
  · `{"t": "err", "msg": …}`     the body's turn failed;  · `{"t": "end"}`.

Closing the iterator (a barge-in, a preemptive draft LiveKit throws away) closes the HTTP response, and the body
cancels the turn the same way LiveKit cancels an in-process stream — `_note_death` keeps his words either way.

What travels with the turn: his last line, the LiveKit speech id the reply belongs to (the body binds the turn's
trace to it, `voice/trace.bind_speech`), and the screen that typed it (`CHILD_ORIGIN`, set around `generate_reply`
by the body's typed door) so every card the turn opens goes back to that screen.
"""
from __future__ import annotations

import contextvars
import os
import time

from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, llm, utils
from livekit.agents.llm import ChatChunk, ChoiceDelta
from loguru import logger

from . import body_link

TURN_PATH = "/api/turn/stream"
FLUSH_S = 0.2           # the bounded wait for the events queued before this turn (see `body_link.flush`)

#: The screen that typed the line this reply answers — set by the body's `/voice/reply`, inherited by the reply task.
CHILD_ORIGIN: contextvars.ContextVar[str] = contextvars.ContextVar("zaelar_child_origin", default="")

#: The `ZAELAR_*` settings the body may push (anything else in the env is this process's own).
ENV_PREFIX = "ZAELAR_"


def last_user_text(chat_ctx) -> str:
    """His last line in the LiveKit chat context — the only thing the body's pipeline reads from it."""
    try:
        items = list(chat_ctx.items)
    except Exception:  # noqa: BLE001
        items = []
    for it in reversed(items):
        if getattr(it, "role", None) != "user":
            continue
        txt = getattr(it, "text_content", None)
        if txt:
            return str(txt).strip()
        content = getattr(it, "content", None)
        if isinstance(content, list):
            return " ".join(c for c in content if isinstance(c, str)).strip()
        return str(content or "").strip()
    return ""


def turn_payload(chat_ctx) -> dict:
    speech_id = ""
    try:
        from livekit.agents.voice.agent_activity import _SpeechHandleContextVar
        speech_id = str(getattr(_SpeechHandleContextVar.get(None), "id", "") or "")
    except Exception:  # noqa: BLE001
        pass
    return {"text": last_user_text(chat_ctx), "speech_id": speech_id, "origin": CHILD_ORIGIN.get()}


def apply_env(env) -> int:
    """The body's live settings onto this process. Only `ZAELAR_*`; an empty value removes it. Returns how many moved."""
    moved = 0
    for k, v in (env or {}).items():
        k = str(k)
        if not k.startswith(ENV_PREFIX):
            continue
        v = "" if v is None else str(v)
        if os.environ.get(k, "") == v:
            continue
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
        moved += 1
    return moved


def _say_again() -> str:
    try:
        from voice.engine.core import langs
        return str(getattr(langs.current_language(), "say_again", "") or "")
    except Exception:  # noqa: BLE001
        return ""


async def remote_llm_node(agent, chat_ctx, tools, model_settings):
    """`Agent.llm_node` in the voice process: the reply's text, read from the body as it is written."""
    from livekit.agents.types import FlushSentinel
    from voice.engine.speech import filler_audio as _fa
    payload = turn_payload(chat_ctx)
    link = body_link.get()
    await link.flush(FLUSH_S)
    t0, said = time.monotonic(), False
    agen = link.stream(TURN_PATH, payload)
    try:
        async for line in agen:
            t = line.get("t")
            if t == "c":
                txt = str(line.get("text") or "")
                if txt:
                    said = True
                    yield txt
            elif t == "filler":
                phrase = str(line.get("text") or "").strip()
                if phrase:
                    _fa.mark_for_strip(phrase)
                    yield phrase + " "
                    yield FlushSentinel()          # its own segment: it sounds now, the reply is segment two
            elif t == "env":
                apply_env(line.get("env"))
            elif t == "err":
                raise RuntimeError(str(line.get("msg") or "the body's turn failed"))
            elif t == "end":
                break
    except RuntimeError as e:
        logger.warning(f"remote brain: turn failed after {time.monotonic() - t0:.2f}s — {e}")
        if not said and (line := _say_again()):
            yield line                             # a lost turn asks him again; it never goes silent
    except OSError as e:                           # the body is not answering at all
        logger.warning(f"remote brain: the body is unreachable ({e!r})")
        if not said and (line := _say_again()):
            yield line
    finally:
        await agen.aclose()


class RemoteBrainLLM(llm.LLM):
    """The session's `llm`: LiveKit only generates a reply when it has one. The reply itself comes from
    `remote_llm_node` (the agent's node override); `chat()` is the same remote call as a plain stream, for any SDK
    path that asks the LLM directly."""

    @property
    def label(self) -> str:
        return "zaelar.remote-brain"

    @property
    def model(self) -> str:
        return "nucleo-flash@body"

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=None, tool_choice=None, extra_kwargs=None) -> llm.LLMStream:
        return _RemoteStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class _RemoteStream(llm.LLMStream):
    async def _run(self) -> None:
        async for piece in remote_llm_node(None, self._chat_ctx, [], None):
            if isinstance(piece, str):
                self._event_ch.send_nowait(ChatChunk(id=utils.shortuuid(),
                                                     delta=ChoiceDelta(role="assistant", content=piece)))

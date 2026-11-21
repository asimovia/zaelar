"""The typed channel's HTTP face: `POST /api/flash/say` and `/api/flash/reset` over `nucleo.cli.turn`.

A line typed through the API goes to the conversation manager (`cli/turn.py`); this module only adds what belongs to
the HTTP edge — the first-run language lock and the chat wall. Mounted by `server/__init__.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Body
from loguru import logger

from nucleo.cli.turn import run_turn

router = APIRouter()


def _wall(role: str, text: str) -> None:
    """Put one line of THIS conversation on the operator's chat wall, live.

    Operator's rule (2026-08-28), watching an unattended round drive the agent while the chat stayed empty:
    «si se opera por voz se transcribe al chat, y si se opera por chat se ve el texto, tanto si se hace
    manualmente sobre el widget del chat como si estamos manejando la conversación a través de la API». One
    conversation, one place to read it, whatever door it came in through.

    It was missing because this channel was built as a HEADLESS test surface (V2-032): nobody was meant to be
    looking. That stopped being true the day the lab agents got a fixed port so the operator could watch a
    round happen — and an agent working silently is indistinguishable from an agent stuck.

    `wall` in the extra is the marker the frontend keys on (`services/sse.js`), NOT the label: a substring
    match on a label is a contract nobody can see from either side. It rides on `kind="brain"` because that
    is already a family the wall subscribes to, so this adds a reader, not a taxonomy (the observability
    families are total and enforced by `test_observer_categories.py`).

    Deliberately NOT emitted as `kind="transcript"`, which is the other event the wall paints: that one also
    feeds the frontend's voice-command fast path (`handleWidgetVoice`), so a probe turn that says "cierra la
    agenda" would be executed TWICE — once by the channel that already executes actions, once by the browser.
    Showing a conversation must never change what it does.

    Never fatal: the wall is a window onto the turn, not part of it.
    """
    if not (text or "").strip():
        return
    try:
        from voice.observer import emit
        emit("brain", "💬 chat (canal de texto)", text=text[:4000],
             role="user" if role == "user" else "assistant",
             extra={"cat": "flash", "wall": "you" if role == "user" else "agent"})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"cli.api: chat wall line not emitted: {e!r}")


@router.post("/api/flash/say")
async def say(text: str = Body(..., embed=True), session: str = Body("default", embed=True),
              ingest: bool = Body(True, embed=True), prompt: bool = Body(False, embed=True),
              model: str = Body("", embed=True), execute: bool = Body(False, embed=True),
              dev: str = Body("", embed=True)) -> dict:
    """His line through the conversation manager, and what it answered (the text channel). `prompt`, `model` and
    `execute` are accepted for older callers: the manager decides with its own model and its own doors."""
    # FIRST-RUN LANGUAGE, on a channel that has no way to ASK (V2-170). The voice pipeline opens a brand-new
    # install with a blocking "what language should I use?" turn and locks the answer; a text channel gets no
    # such turn, so without this it stays on the product default (English) for as long as it lives. That is not
    # only how the reply reads: `nucleo/flash/site_catalog.py` resolves its LOCALE from the same code, so a
    # Spanish errand was being handed opentable.com and ticketmaster.com instead of thefork.es and entradas.es.
    #
    # It lives HERE, at the HTTP edge, and not inside `run_turn`: that function is also how the suite drives a
    # turn IN-PROCESS, and a detector that persists a language from there flips `ZAELAR_LANGUAGE` for every test
    # that runs after it (measured — `test_suite_isolation.py` caught exactly that). The edge is the honest
    # layer anyway: it is where there is a real operator on the other side.
    #
    # NOT mirrored into the voice provider on purpose: a silent lock there would race the modal's question and
    # could commit the wrong language before it is answered. A no-op once a language is chosen; never raises.
    try:
        from i18n.init import detect as _lang_detect
        await _lang_detect.ensure_for_text_async(text)   # awaited: turn 1 gets it; the model call is off the loop
    except Exception as e:  # noqa: BLE001 — the line still runs; only the first-run guess is skipped
        logger.debug(f"cli.api: first-run language not locked: {e!r}")
    # TO THE WALL, before anything else: the turn may take seconds and the operator must see the request now.
    # If it were rendered at the end, the screen would be silent while the agent works — exactly when it is watched.
    _wall("user", text)
    # `dev` — the screen this line is typed from (`desktop:…` / `mobile:…`), as `/api/chat` carries it. Without it a
    # text test runs with no asking screen, and whatever depends on WHERE he asked (which player sounds, V2-861) is
    # untestable by text. Empty keeps today's behaviour.
    if (dev or "").strip():
        from voice import screens as _screens
        _screens.begin_turn(dev)
        _screens.ORIGIN.set(_screens.clean(dev))
    res = await run_turn(text, sid=session, ingest=ingest, model=model, execute=execute, door=True)
    # `reply` is a LIST of sentences (a turn may say several). Join them instead of calling `str()`: stringifying
    # the list would render `['I will look for them now.']` on the wall, including brackets and quotes.
    _reply = res.get("reply")
    _wall("agent", " ".join(str(x) for x in _reply) if isinstance(_reply, list) else str(_reply or ""))
    return res                               # (`prompt`, the old turn's composed prompt, went with the unplug)


@router.post("/api/flash/reset")
async def reset(session: str = Body("default", embed=True)) -> dict:
    """A barrier for headless runs: every completed memory write is visible to the next line (does NOT touch memory;
    use `make reset` for that)."""
    # A reset is an explicit causal barrier in headless tests: all completed memory writes must be visible in the
    # first turn of the new window. It does not run on the physical voice hot path.
    from memory.api import state_cache as memory_cache
    await memory_cache.refresh()
    return {"ok": True, "session": session or "default"}

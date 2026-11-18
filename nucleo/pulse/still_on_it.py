"""nucleo/pulse/still_on_it.py — while something he asked for is being worked on and nobody is talking, he is told it goes on.

Measured on his engine (2026-11-18): an errand ran for six minutes and he heard nothing of it — «you don't even say
one moment, or that you are on it; it looks as if you were not listening or not working». A person helping someone
says «still on it» now and then, and says where it is.

The pulse asks `beat` once per tick. It speaks when ALL hold: an errand RUNS (not waiting on him, not queued, not
paused); a voice session is live; nobody has said anything — he or the agent — for a wait drawn at random between
`MIN_S` and `MAX_S` after the last thing said (a new wait is drawn every time somebody speaks, so it never falls
into a rhythm); and his own rule allows it. The line is a FACT worded by a model (`nucleo/wording.py`): that it goes
on, and the step it is at when the errand has reported one.

It is a courtesy, never a debt: a line that could not be said is dropped — not pushed to his phone, not owed, not
retried when the errand is long over (`notices.notify(ephemeral=True)`). And it is HIS to silence: the genesis style
knob `still_working_lines` is a `voice` row of the rules table, so «no need to tell me you are still on it» written
once as a rule turns it off (`nucleo/style_policy.still_working_lines`).
"""
from __future__ import annotations

import random
import time

from loguru import logger

#: The bounds of the silence after which he is told it goes on — a new wait is drawn inside them every time.
MIN_S, MAX_S = 5.0, 40.0
#: The kinds of event that are «somebody said something» in the conversation: his turns, ours, a filler, a notice —
#: never bare voice activity (a television in the room is not him talking to us).
SAID = frozenset({"transcript", "bot_speech", "filler", "notify"})
#: How far back the event ring is read for the last thing said.
_LOOK_BACK = 400
#: The fact the line words. `{step}` is the step the errand reported, when it reported one.
FACT = ("You are still working on what he asked for; it is not finished yet. {step}Tell him so in a few words — no "
        "apology, no promise of when, and nothing he has not been told to expect.")
STEP = "Where it is right now: {phase}. "

_state: dict = {"anchor": 0.0, "wait": 0.0}


def _draw() -> float:
    return random.uniform(MIN_S, MAX_S)


def last_said_at() -> float:
    """When anybody last said anything this session (epoch seconds), read off the event ring; 0.0 when nothing was."""
    try:
        from voice import observer
        for ev in reversed(observer.debug_events()[-_LOOK_BACK:]):
            if ev.get("kind") in SAID:
                return float(ev.get("t_ms") or 0.0) / 1000.0
    except Exception as e:  # noqa: BLE001 — unread: treated as «just said», so nothing speaks on a guess
        logger.debug(f"still_on_it: the event ring unread — {e!r}")
        return time.time()
    return 0.0


def running(sessions: list[dict]) -> list[dict]:
    """The errands that are being WORKED on right now: not waiting on him, not queued, not paused."""
    return [s for s in sessions or [] if s.get("waiting_on") != "user" and s.get("status") != "queued"
            and not s.get("paused")]


def _allowed() -> bool:
    try:
        from nucleo import style_policy
        return style_policy.still_working_lines()
    except Exception as e:  # noqa: BLE001 — a rule that cannot be read is not a licence to speak
        logger.debug(f"still_on_it: his rule unread — {e!r}")
        return False


def _floor_free() -> bool:
    """A voice session is live and neither of them is speaking right now."""
    try:
        from voice import proactive
        return proactive.has_voice() and not (proactive.user_speaking() or proactive.bot_speaking()
                                              or proactive.hushed())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"still_on_it: the floor unread — {e!r}")
        return False


def due(sessions: list[dict], now: float) -> dict | None:
    """The errand to speak for on this tick, or None. Draws a new wait whenever the last thing said has moved."""
    run = running(sessions)
    if not run:
        _state.update(anchor=0.0, wait=0.0)
        return None
    last = max(last_said_at(), min(now - float(s.get("age_s") or 0) for s in run))   # never before it started
    if last != _state["anchor"]:
        _state.update(anchor=last, wait=_draw())
    if now - last < _state["wait"] or not _allowed() or not _floor_free():
        return None
    return max(run, key=lambda s: int(s.get("age_s") or 0))      # the one he has waited longest for


def line(s: dict, say) -> str:
    """The line for errand `s`, worded for him; the language's own line is the example and the last resort. Blocking —
    call it off the loop."""
    from nucleo import wording
    plain = str(say("still_on_it") or "")
    phase = " ".join(str(s.get("phase") or "").split())[:120]
    fact = FACT.format(step=STEP.format(phase=phase) if phase else "")
    return wording.word(fact, about=str(s.get("title") or s.get("goal") or "")[:160], examples=(plain,),
                        fallback=plain)


async def beat(sessions: list[dict], now: float, say) -> bool:
    """One tick: say the line when it is due. True when a line was handed to the mouth. Never raises."""
    try:
        s = due(sessions, now)
        if s is None:
            return False
        import asyncio

        from nucleo.pulse import notices
        text = await asyncio.to_thread(line, s, say)
        _state.update(anchor=time.time(), wait=_draw())          # said or not, the next one waits its own turn
        if not text:
            return False
        uid = str(s.get("uid") or s.get("id") or "")
        await notices.notify("zaelar", text, key=f"still:{uid}:{int(now)}", task_id=uid, kind="info",
                             ephemeral=True, opens_window=False)
        return True
    except Exception as e:  # noqa: BLE001 — a courtesy never breaks the pulse
        logger.debug(f"still_on_it: no line this tick — {e!r}")
        return False

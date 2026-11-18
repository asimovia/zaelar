"""nucleo/pulse/still_on_it.py — while something he asked for is being worked on and nobody is talking, he is told it goes on.

Measured on his engine (2026-11-18): an errand ran for six minutes and he heard nothing of it — «you don't even say
one moment, or that you are on it; it looks as if you were not listening or not working». A person helping someone
says «still on it» now and then, and says where it is.

The pulse asks `beat` once per tick. It speaks when ALL hold: an errand RUNS (not waiting on him, not queued, not
paused); a voice session is live; nobody has said anything — he or the agent — for a wait drawn at random between
`MIN_S` and `MAX_S` after the last thing said (a new wait is drawn every time somebody speaks, so it never falls
into a rhythm); and his own rule allows it. The line is a FACT worded by a model (`nucleo/wording.py`): that it goes
on, and the step it is at when the errand has reported one.

An errand that has NOT started — the admission gate holds it while the host has no room — is never told as «still
on it»: after `HELD_FIRST_S` he hears that it has not begun, why, and that he can have it started anyway; then again
at intervals that double (`held_due`). Measured the same day: twenty minutes held and not a word.

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
        for ev in reversed(list(observer._events[-_LOOK_BACK:])):     # the tail only: this runs on every beat
            if ev.get("kind") in SAID:
                return float(ev.get("t_ms") or 0.0) / 1000.0
    except Exception as e:  # noqa: BLE001 — unread: treated as «just said», so nothing speaks on a guess
        logger.debug(f"still_on_it: the event ring unread — {e!r}")
        return time.time()
    return 0.0


def running(sessions: list[dict]) -> list[dict]:
    """The errands that are being WORKED on right now: not waiting on him, not queued, not paused, not held."""
    return [s for s in sessions or [] if s.get("waiting_on") != "user" and s.get("status") != "queued"
            and not s.get("paused") and not s.get("held")]


def held(sessions: list[dict]) -> list[dict]:
    """The errands that have NOT started: the admission gate holds them (`workers/envelope`)."""
    return [s for s in sessions or [] if s.get("held") and s.get("waiting_on") != "user"]


#: A held errand is said after `HELD_FIRST_S` of hold, then at intervals that double up to `HELD_MAX_S`: he must know
#: it has not begun and that he can start it anyway, without hearing it every half minute for twenty.
HELD_FIRST_S, HELD_MAX_S = 20.0, 600.0
_held_said: dict = {}      # errand → (how many times it was said, when last)


def held_due(sessions: list[dict], now: float) -> dict | None:
    """The held errand to speak for on this tick, or None: the one held longest whose own interval has passed."""
    live = {str(s.get("uid") or s.get("id") or ""): s for s in held(sessions)}
    for k in [k for k in _held_said if k not in live]:
        _held_said.pop(k, None)
    for key, s in sorted(live.items(), key=lambda kv: -int(kv[1].get("held_s") or 0)):
        n, last = _held_said.get(key, (0, 0.0))
        wait = min(HELD_FIRST_S * (2 ** n), HELD_MAX_S)
        since = float(s.get("held_s") or 0) if not n else now - last
        if since >= wait and _allowed() and _floor_free():
            return s
    return None


def held_line(s: dict, say) -> str:
    """The line for a held errand: the truth — not started, why, and that he can start it anyway. Blocking."""
    from nucleo import wording
    plain = str(say("still_held") or "")
    return wording.word(wording.FACTS["still_held"], about=str(s.get("title") or s.get("goal") or "")[:160],
                        examples=(plain,), fallback=plain)


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
        import asyncio

        from nucleo.pulse import notices
        h = held_due(sessions, now)
        if h is not None:                                        # not started: said as that, never as «still on it»
            uid = str(h.get("uid") or h.get("id") or "")
            _held_said[uid] = (_held_said.get(uid, (0, 0.0))[0] + 1, now)
            text = await asyncio.to_thread(held_line, h, say)
            if text:
                await notices.notify("zaelar", text, key=f"held:{uid}:{int(now)}", task_id=uid, kind="info",
                                     ephemeral=True)             # it opens his window: «start it anyway» is expected
            return bool(text)
        s = due(sessions, now)
        if s is None:
            return False
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

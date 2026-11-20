"""The `Mouth` port's VOICE half (V2-941, v3.1 §1.7, B9): one primitive, the voice process's `/voice/say`.

A line ordered on the voice channel, in a session of the manager, is said through the live session's client with the
manager's `say_id` as its alias and `conv` set — so the voice process reads back how much of it SOUNDED
(`spoken_chars`, from the speech's own chat item, cut to what played) and keeps it off the old turn's record. The
acks reach the conversation in its own thread (`entry.ack`): its first line is `SayStarted`; its `done` is
`SayEnded` — `cut` when it was interrupted, `played` when not, with `spoken_chars` as what was heard
(`agent_estimate`); an error, a lost connection or no `done` is `unknown`, never «heard». A stop is the same door with
`cut` and no text. With no voice session of the manager there is no voice half: the line is shown, as before.
"""
from __future__ import annotations

import asyncio
import time

from conversation.mouth import SayEnded, SayStarted


def _now() -> int:
    return int(time.time() * 1000)


def _live():
    """The live session's client when it is a session of the manager, else None."""
    from voice import remote_session as rs
    sess, cl = rs._M.get("session"), rs._M.get("client")
    d = getattr(sess, "_conversation_switch", None)
    if sess is None or cl is None or d is None or not d.on or getattr(cl, "_loop", None) is None:
        return None
    return cl


def speak(order, ack) -> bool:
    """Start saying `order` on the voice; `ack(signal)` hands each ack to the conversation. False: no voice half."""
    cl = _live()
    if cl is None:
        return False
    payload = {"text": order.text, "alias": order.say_id, "conv": True, "allow_interruptions": True}

    async def play() -> None:
        payload["env"] = cl.env_diff()         # on the body's loop, the one that keeps what was sent
        started = False
        try:
            async for line in cl.say_stream(payload):
                if not started and "id" in line and not line.get("done"):
                    started = True
                    ack(SayStarted(order.say_id, _now()))
                if line.get("done"):
                    if line.get("error"):
                        break
                    ack(SayEnded(order.say_id, "cut" if line.get("interrupted") else "played",
                                 int(line.get("spoken_chars") or 0), _now(), order.endpoint, "agent_estimate"))
                    return
        except Exception as e:  # noqa: BLE001 — a line whose end was never heard is «unknown», said, never «heard»
            from voice import observer
            observer.emit("alert", "a line of the manager's voice ended unheard", text=repr(e)[:200])
        ack(SayEnded(order.say_id, "unknown", None, _now(), order.endpoint, "unknown"))

    asyncio.run_coroutine_threadsafe(play(), cl._loop)
    return True


def stop() -> bool:
    """Our voice stops now: the same door, `cut` and no text. With the voice on the old path (text only) it is that
    voice that stops — his «stop» typed to the manager never leaves it talking. False: no voice at all."""
    cl = _live()
    if cl is not None:
        cl.post_soon("/voice/say", {"text": "", "cut": True, "conv": True})
        return True
    from voice import remote_session as rs
    old = rs._M.get("client")
    if rs._M.get("session") is None or old is None or getattr(old, "_loop", None) is None:
        return False
    old.post_soon("/voice/say", {"text": "", "cut": True})
    return True

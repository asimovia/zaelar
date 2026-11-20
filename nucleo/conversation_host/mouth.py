"""The `Mouth` port of a switched session (V2-941, B5 and B9; plan v3.2 C2/C4). Its rows are the old turn's:

  · a line SHOWN (no voice session of the manager, or the text channel) is the `transcript` row, role assistant, at
    once and whole, and is acknowledged as shown;
  · a line SAID (`voice_mouth.speak`) is announced as owed (`brain` reply, its trace) BEFORE its voice can start, so
    the wall paints it when its voice starts — the line's trace is adopted at `SayStarted`, so the voice's
    `bot_speech` carries it — and its `transcript` row is written when it ENDS, with what sounded (cut to
    `heard_chars`). Its acks come from the voice. A line whose voice died before it started never claims it sounded:
    a reply is written whole, marked `sounded: false`; a notice writes nothing and goes back to its retry;
  · a NOTICE (a line owed through the notices ledger: `notice_key`) keeps its 🔔 card, painted when its voice starts
    (`notice_claim.paint`), as `notify` paints every notice, and its row when it has sounded.

`stop` cuts our voice now.
"""
from __future__ import annotations

from typing import Callable

from conversation.mouth import SayEnded, SayStarted


REPLY = "💬 conversation: reply"        # the wall's owed line (a `brain` reply, role assistant, with its trace)


def trace_of(order) -> str:
    """The turn our line answers (`turns.corr`, C16) — a failure line's too — else its request's own trace (a
    notice's line has no turn)."""
    from nucleo.conversation_host import turns
    rid = str(order.request_id or "")
    return turns.known(turns.iv_of(rid)) or (rid[2:] if rid.startswith("r_") else rid)


def _card(order) -> None:
    from nucleo.pulse import notice_claim
    notice_claim.paint(order.notice_key)


class WallMouth:
    def __init__(self, clock, said: Callable[[str, str], None] | None = None, voice=None,
                 ack_later: Callable | None = None) -> None:
        self.ack: Callable | None = None              # set by the boot: the conversation's `ack`
        self._clock, self._said = clock, said
        self.voice = voice                            # the voice half (`voice_mouth`), or None: shown only
        self.ack_later: Callable = ack_later or (lambda sig: None)   # an ack from another thread, handed in order

    async def say(self, order) -> None:
        from voice import observer
        extra = {"trace": trace_of(order), "conv_say": order.say_id, "conv": True}
        notice = bool(getattr(order, "notice_key", None))
        if self._said is not None:
            self._said(order.request_id, order.text)
        voiced = "voice" in order.channels and self.voice is not None
        if voiced and not notice:                       # owed BEFORE its voice can start it
            observer.emit("brain", REPLY, text=order.text, role="assistant", extra=extra, piece="f_mouth")
        if voiced and self.voice.speak(order, self._sounded(order)):
            return                                      # its acks come from the voice: what sounded, or «unknown»
        from nucleo.conversation_host import wall
        wall.ours(order, "shown")
        if notice:
            _card(order)                                # shown: its card, as every notice
        else:
            observer.emit("transcript", "zaelar", text=order.text, role="assistant", extra=extra, piece="f_mouth")
        if self.ack is not None:
            now = self._clock.now_ms()
            self.ack(SayStarted(order.say_id, now))
            self.ack(SayEnded(order.say_id, "played", len(order.text), now, order.endpoint, "shown"))

    def _sounded(self, order) -> Callable:
        """The voice's acks of one line, on their way to the conversation: at its start the line's trace is the voice's
        (its `bot_speech` paints the owed line); at its end its row is written with what sounded."""
        notice, started = bool(getattr(order, "notice_key", None)), []

        def ack(sig) -> None:
            from nucleo.conversation_host import wall
            from voice import observer, trace
            if isinstance(sig, SayStarted):
                started.append(sig.t_ms)
                wall.ours(order, "started")
                trace.adopt(trace_of(order))
                if notice:
                    _card(order)
            elif isinstance(sig, SayEnded) and (started or not notice):
                if not started:                         # never started: on the wall whole, never said to have sounded
                    wall.ours(order, "shown")
                else:
                    wall.ours(order, "ended", sig.heard_chars)
                heard = order.text if sig.heard_chars is None else order.text[:max(0, sig.heard_chars)]
                if heard.strip():
                    observer.emit("transcript", "zaelar", text=heard, role="assistant",
                                  extra={"trace": trace_of(order), "conv_say": order.say_id, "conv": True,
                                         "outcome": sig.outcome if started else "unknown",
                                         **({} if started else {"sounded": False})}, piece="f_mouth")
            self.ack_later(sig)
        return ack

    def stop(self, endpoint, *, reason: str) -> None:
        if self.voice is not None:
            self.voice.stop()

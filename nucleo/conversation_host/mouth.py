"""The `Mouth` port of a switched session — its TEXT half (V2-941, B5): a line goes to the chat column of every
screen, as the old turn's reply does (`transcript`, role assistant), and is acknowledged at once as SHOWN, whole. The
voice half (the voice process's `say` with its cut and what sounded) is B9; until then a line with the voice channel
is shown, never spoken, and `voice_spoken` stays false in its ack's source.
"""
from __future__ import annotations

from typing import Callable

from conversation.mouth import SayEnded, SayStarted


class WallMouth:
    def __init__(self, clock, said: Callable[[str, str], None] | None = None) -> None:
        self.ack: Callable | None = None              # set by the boot: the conversation's `ack`
        self._clock, self._said = clock, said

    async def say(self, order) -> None:
        from voice import observer
        observer.emit("transcript", "zaelar", text=order.text, role="assistant",
                      extra={"trace": order.request_id[2:] if order.request_id.startswith("r_") else order.request_id,
                             "conv_say": order.say_id}, piece="f_mouth")
        if self._said is not None:
            self._said(order.request_id, order.text)
        if self.ack is not None:
            now = self._clock.now_ms()
            self.ack(SayStarted(order.say_id, now))
            self.ack(SayEnded(order.say_id, "played", len(order.text), now, order.endpoint, "shown"))

    def stop(self, endpoint, *, reason: str) -> None:
        return None                                     # nothing sounds yet: the voice half is B9

"""The `Mouth` port of a switched session (V2-941, B5 and B9). Its TEXT half: a line goes to the chat column of every
screen, as the old turn's reply does (`transcript`, role assistant). A line on the VOICE channel, with a voice session
of the manager live, is also said (`voice_mouth.speak`), and its acks — what sounded — come from the voice; otherwise
it is acknowledged at once as SHOWN, whole. `stop` cuts our voice now.
"""
from __future__ import annotations

from typing import Callable

from conversation.mouth import SayEnded, SayStarted


class WallMouth:
    def __init__(self, clock, said: Callable[[str, str], None] | None = None, voice=None,
                 ack_later: Callable | None = None) -> None:
        self.ack: Callable | None = None              # set by the boot: the conversation's `ack`
        self._clock, self._said = clock, said
        self.voice = voice                            # the voice half (`voice_mouth`), or None: shown only
        self.ack_later: Callable = ack_later or (lambda sig: None)   # an ack from another thread, handed in order

    async def say(self, order) -> None:
        from voice import observer
        observer.emit("transcript", "zaelar", text=order.text, role="assistant",
                      extra={"trace": order.request_id[2:] if order.request_id.startswith("r_") else order.request_id,
                             "conv_say": order.say_id}, piece="f_mouth")
        if self._said is not None:
            self._said(order.request_id, order.text)
        if "voice" in order.channels and self.voice is not None and self.voice.speak(order, self.ack_later):
            return                                      # its acks come from the voice: what sounded, or «unknown»
        if self.ack is not None:
            now = self._clock.now_ms()
            self.ack(SayStarted(order.say_id, now))
            self.ack(SayEnded(order.say_id, "played", len(order.text), now, order.endpoint, "shown"))

    def stop(self, endpoint, *, reason: str) -> None:
        if self.voice is not None:
            self.voice.stop()

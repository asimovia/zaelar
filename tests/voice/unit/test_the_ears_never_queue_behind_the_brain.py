"""V2-887 — the voice's VAD inference never waits in a thread pool: no blocking work of ours can queue in front of it.

The Silero plugin runs every 32 ms window on the loop's DEFAULT pool, shared with every blocking call awaited on the
voice job's loop. When those calls are slow (a host short of memory), the windows queue behind them, END_OF_SPEECH
comes late and the turn reaches the chat late. Here the default pool is saturated with slow blocking calls and one
second of audio is pushed: our VAD (inference inline) answers within that second; the plugin's own VAD (the disarm)
answers nothing.
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest
from livekit import rtc

from voice.engine.speech.vad import silero as S


def _events_within_a_second_of_audio(vad) -> int:
    async def main():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(__import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=4))
        for _ in range(8):
            loop.run_in_executor(None, time.sleep, 1.6)    # the brain's blocking work, slowed by a busy machine
        st = vad.stream()
        seen = []

        async def read():
            async for ev in st:
                seen.append(ev.type)
        task = asyncio.create_task(read())
        frame = rtc.AudioFrame(data=np.zeros(320, dtype=np.int16).tobytes(), sample_rate=16000, num_channels=1,
                               samples_per_channel=160)
        for _ in range(100):                                # one second of audio, in real time
            st.push_frame(frame)
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.2)
        n = len(seen)
        task.cancel()
        return n
    return asyncio.run(main())


def test_the_inline_vad_keeps_up_while_the_default_pool_is_full():
    assert _events_within_a_second_of_audio(S.build()) > 10


def test_disarmed_the_plugins_own_vad_waits_behind_the_brain():
    from livekit.plugins import silero as plugin
    vad = plugin.VAD.load(prefix_padding_duration=0.8, activation_threshold=0.5)
    assert type(vad) is plugin.VAD, "the disarm did not take"
    assert _events_within_a_second_of_audio(vad) == 0

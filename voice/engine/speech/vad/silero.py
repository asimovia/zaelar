"""Silero VAD (bundled ONNX, no runtime download). Local in both profiles.

THE EARS NEVER WAIT IN A QUEUE (V2-887). The plugin runs each 32 ms window with `loop.run_in_executor(None, …)` — the
loop's DEFAULT thread pool, shared with every other blocking call awaited on the voice job's loop. One window is
≈0.1 ms of ONNX, so the hop to a pool and back was the whole cost: when that pool was busy or the host was slow, the
windows queued, the SDK's own delay counter climbed («inference is slower than realtime»), END_OF_SPEECH came late and
the turn reached the chat late. The window now runs INLINE on the stream's loop and returns an already-resolved
future: no thread hop, no queue, no GIL round trip. A backlog left by a host stall drains at hundreds of times real
time instead of growing, so no stale audio is dropped. Nothing else of the plugin changes.
"""
from __future__ import annotations

import asyncio
import os

from livekit.plugins import silero as _silero

from . import registry


class _InlineLoop:
    """The stream's event loop, except that the plugin's `run_in_executor(None, f, …)` runs `f` right here."""

    def __init__(self, loop):
        self._loop = loop

    def run_in_executor(self, executor, func, *args):
        if executor is not None:
            return self._loop.run_in_executor(executor, func, *args)
        fut = self._loop.create_future()
        try:
            fut.set_result(func(*args))
        except BaseException as e:  # noqa: BLE001 — the plugin awaits it and sees the same error a pool would raise
            fut.set_exception(e)
        return fut

    def __getattr__(self, name):
        return getattr(self._loop, name)


class VAD(_silero.VAD):
    """Silero with its inference inline (see the module docstring)."""

    def stream(self):
        s = super().stream()
        # The plugin reads `_loop` at its first inference, after this returns. If a new plugin version stops using it,
        # fail loudly here instead of silently queueing the ears again.
        assert isinstance(getattr(s, "_loop", None), asyncio.AbstractEventLoop), "silero stream has no _loop to wrap"
        s._loop = _InlineLoop(s._loop)
        return s


@registry.register("silero")
def build():
    # Two levers, both env-overridable, in tension (anti-clipping vs. anti-noise):
    #   · prefix_padding_duration — how much audio BEFORE the detected onset is prepended to the turn. 0.8s recovers the
    #     first word during a fast start (fix for "you eat the first word"). It is KEPT at 0.8 → even if
    #     we raise the threshold, the onset is not lost because the padding already captures it.
    #   · activation_threshold — VOICE probability (Silero, 0-1) required to start capturing. 2026-07-12: 0.4→0.5
    #     (background-noise robustness requested by the operator): at 0.4, "almost-voice" noise triggered a turn; 0.5 requires
    #     something more clearly human. DO NOT raise it further (0.55+ started eating soft onsets despite the padding). The
    #     MAIN filter for DISTANT noise is the RMS energy gate (`stt_rms_gate`=0.02): this complements it.
    return VAD.load(
        prefix_padding_duration=float(os.getenv("ZAELAR_VAD_PREFIX_PAD", "0.8")),
        activation_threshold=float(os.getenv("ZAELAR_VAD_ACTIVATION", "0.5")),
    )

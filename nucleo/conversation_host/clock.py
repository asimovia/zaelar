"""The `Clock` port on the machine's time: wall milliseconds, monotonic milliseconds, and a sleep on the loop."""
from __future__ import annotations

import asyncio
import time


class SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def mono_ms(self) -> int:
        return int(time.monotonic() * 1000)

    async def sleep_until(self, mono_ms: int) -> None:
        await asyncio.sleep(max(0.0, (mono_ms - self.mono_ms()) / 1000))

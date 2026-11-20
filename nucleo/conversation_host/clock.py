"""The `Clock` port on the machine's time: wall milliseconds, monotonic milliseconds, a sleep on the loop, and the
local zone at an instant — the same local time the old turn reads (`time.localtime`), with its name and offset."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime


class SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def mono_ms(self) -> int:
        return int(time.monotonic() * 1000)

    async def sleep_until(self, mono_ms: int) -> None:
        await asyncio.sleep(max(0.0, (mono_ms - self.mono_ms()) / 1000))

    def zone(self, now_ms: int) -> tuple[int, str]:
        """(offset in minutes, name) of the local zone at `now_ms` — summer time included."""
        local = datetime.fromtimestamp(now_ms / 1000).astimezone()
        offset = local.utcoffset()
        return int(offset.total_seconds() // 60) if offset is not None else 0, local.tzname() or ""

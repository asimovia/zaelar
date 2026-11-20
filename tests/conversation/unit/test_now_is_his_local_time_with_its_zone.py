"""NOW is his local time, with its zone named and its offset (node 13.105, V2-941, v3.1 B7l — live on a text-only
engine: «what time is it?» at 08:54 CET was answered «7:54»).

The prompt's NOW block took the zone from a field the manager never filled: every time it gave was UTC. The `Clock`
port now says the local zone at an instant (`zone(now_ms)`: offset and name — summer time included), the host's clock
reads the same local time the old turn reads, and NOW writes it with its name and offset; the times of his entries in
INPUT use the same zone. A clock with no zone is UTC, said as UTC.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from conversation.ports import Done
from conversation.testing.scripted_model import reply
from nucleo.conversation_host.clock import SystemClock
from tests.conversation.unit.convkit import Harness

#: 2026-11-20 07:54 UTC — 08:54 in Madrid (CET, UTC+01:00)
AT = int(datetime(2026, 11, 20, 7, 54, tzinfo=timezone.utc).timestamp() * 1000)


def test_the_prompt_says_his_local_time_with_its_zone(store):
    h = Harness(store, grace=False)
    h.clock.wall0, h.clock._zone = AT, (60, "CET")
    h.model.default = lambda ids: [reply("w1"), Done()]
    h.typed("w0", 0)
    h.settle(2000)
    state = h.model.calls[0].prompt.state
    assert "Fri 2026-11-20 08:54 CET (UTC+01:00)" in state and "07:54" not in state
    assert "· 01:00:00]" in h.model.calls[0].prompt.input               # his entry (sealed at 0 UTC), same zone


def test_a_clock_with_no_zone_says_utc(store):
    h = Harness(store, grace=False)
    h.clock.wall0 = AT
    c = h.clock                                                            # the port's zone is optional
    h.conv.clock = type("Bare", (), {"now_ms": lambda self: c.now_ms(), "mono_ms": lambda self: c.mono_ms(),
                                     "sleep_until": lambda self, t: c.sleep_until(t)})()
    h.model.default = lambda ids: [reply("w1"), Done()]
    h.typed("w0", 0)
    h.settle(2000)
    assert "07:54 UTC (UTC+00:00)" in h.model.calls[0].prompt.state


def test_the_hosts_clock_reads_the_local_zone_summer_time_included():
    before = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Madrid"
    time.tzset()
    try:
        july = int(datetime(2026, 7, 1, 12, tzinfo=timezone.utc).timestamp() * 1000)
        assert SystemClock().zone(AT) == (60, "CET") and SystemClock().zone(july) == (120, "CEST")
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        time.tzset()

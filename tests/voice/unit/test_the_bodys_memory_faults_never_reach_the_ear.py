"""The body's memory work never reaches the ear (V2-891, node 3.191).

The voice process reads its audio in 10 ms windows; a window that arrives late is a hole in what the VAD hears and,
past the ear's websocket timeout, a sentence cut in pieces (Deepgram 1011, measured live). Embedded, the ear was a
THREAD of the body, so every stretch the body spent inside one C call holding the interpreter — allocating and
zero-filling a large buffer, a full garbage collection over a big heap, a page fault on memory the host had swapped
out — was a stretch the ear could not run.

This test runs the measurement against the topology the engine actually uses (`voice.child_process.embedded()`):
an «ear» loop that wakes every 10 ms and records how late each wake is, placed where the engine places the voice —
its own interpreter (`python -m …`, as `VoiceChild` spawns it) or, embedded, a thread of the process doing the
work. Meanwhile this process (the body) writes 1.5 GB page by page and, holding it, runs the long C calls that keep
the interpreter (a sort of two million values, a full collection over a million objects). Every 10 ms window that came due while the ear could not run counts, each late by its own wait — a single
stall of 300 ms is thirty late windows, not one. Bound: the ear's p99 window lateness ≤ 50 ms.

Disarm (seen red): `ZAELAR_VOICE_EMBEDDED=1` — the ear becomes a thread of the body and its p99 lateness goes to
hundreds of milliseconds.
"""
from __future__ import annotations

import gc
import json
import subprocess
import sys
import threading
import time

from voice import child_process

PERIOD_S = 0.010
P99_MAX_MS = 50.0
TOUCH_MB = 1536
CHUNK_MB = 512

_EAR = r"""
import json, sys, time
period, run_s = float(sys.argv[1]), float(sys.argv[2])
late, end = [], time.monotonic() + run_s
print("ready", flush=True)
nxt = time.monotonic() + period
while time.monotonic() < end:
    time.sleep(max(0.0, nxt - time.monotonic()))
    now = time.monotonic()
    while nxt <= now:                      # every window that came due while it slept is late by its own wait
        late.append((now - nxt) * 1000.0)
        nxt += period
print(json.dumps(late), flush=True)
"""


def _ear_thread(run_s: float, out: list) -> None:
    nxt = time.monotonic() + PERIOD_S
    end = time.monotonic() + run_s
    while time.monotonic() < end:
        time.sleep(max(0.0, nxt - time.monotonic()))
        now = time.monotonic()
        while nxt <= now:
            out.append((now - nxt) * 1000.0)
            nxt += PERIOD_S


def _body_work(seconds: float) -> None:
    """What a busy body short of memory does to its interpreter: it holds 1.5 GB it has touched page by page, and
    meanwhile runs the long C calls that never let go of the interpreter — a full garbage collection over a big heap,
    a sort of millions of values — for the whole time the ear listens (the measurement is of the overlap)."""
    import random
    held = [b"\x01" * (CHUNK_MB * 2 ** 20) for _ in range(TOUCH_MB // CHUNK_MB)]   # every page written
    junk = [{"i": i} for i in range(1_000_000)]
    values = [random.random() for _ in range(2_000_000)]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        sorted(values)                                    # one C call: the interpreter is held throughout
        gc.collect()                                      # a full collection over the heap: the same
    del held, junk, values
    gc.collect()


def _p99(xs: list) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.99 * len(xs)))] if xs else 0.0


def _measure(run_s: float = 3.0) -> list:
    if child_process.embedded():
        late: list = []
        t = threading.Thread(target=_ear_thread, args=(run_s, late), daemon=True)
        t.start()
        _body_work(run_s - 0.6)
        t.join(run_s + 10)
        return late
    proc = subprocess.Popen([sys.executable, "-c", _EAR, str(PERIOD_S), str(run_s)], stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "ready"
    _body_work(run_s - 0.6)
    out, _ = proc.communicate(timeout=run_s + 30)
    return json.loads(out.strip().splitlines()[-1])


def test_the_ear_keeps_its_windows_while_the_body_touches_a_gigabyte_and_a_half():
    late = _measure()
    assert len(late) > 100, "the ear barely ran: the measurement broke, not the topology"
    p99 = _p99(late)
    assert p99 <= P99_MAX_MS, (f"the ear's p99 lateness was {p99:.0f} ms (max {max(late):.0f} ms) while the body "
                               f"worked — the voice is sharing the body's interpreter")

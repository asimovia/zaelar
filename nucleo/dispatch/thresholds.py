"""nucleo/dispatch/thresholds.py — the CLOCKS of a background task, defined once (V2-354).

Extracted from `dispatch.py` to pay the architecture ratchet, with the same criterion and precedent as
`dispatch_confirm.py` and `dispatch_prompts.py`: they are constants without a single dependency on the record, and
several sites read them — the supervisor of `nucleo/pulse/loop.py`, the whisperer's gate (`nucleo/whisper/gate.py`)
and `dispatch.pending_summaries()`. They are re-exported from `dispatch` because that is still the public contract and
there are callers that import them from there; this is a move, not an interface change.

**Why one definition and not one per consumer**: two copies of these numbers is exactly how the operator ends up
hearing one thing from the proactive notice and another from the agent he just asked.
"""
from __future__ import annotations

import os

#: How much can estar a worker live SIN EMITIR NADA before of llamarlo stalled. «Encallado = silent», and esa
#: definition fue a correccion measurement: until the 2026-08-02 esto miraba the EDAD of the task, so that any
#: worker that pasara of three minutos is declaraba stalled although estuviera emitting each five segundos — the
#: Susurro is it creia, re-escalaba, and salian two and three workers haciendo the same work.
STUCK_SECS = float(os.getenv("WORKER_STUCK_SECS", "180"))

#: How long a task WITH a plan may go without completing one step (longer than `STUCK_SECS`: it is working, not
#: silent). Calibrated on two runs, 331 s and 236.8 s stuck at the first step; the operator's bar: «a search is
#: done in a minute, two or three at most», so 150 s for ONE step of a plan stays generous.
NO_STEP_SECS = float(os.getenv("WORKER_NO_STEP_SECS", "150"))

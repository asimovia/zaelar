"""nucleo/play — ONE linear programme for a declared action (V2-909).

A request the turn reads as ONE declared action of one of our widgets runs the same steps every time:

    understood → resolving → (asking ⇄ his answer)* → (confirming ⇄ his yes/no)? → executing → executed
                                                                                                 │
                           reported ◄── done | failed | unverified | cancelled ◄── verifying ◄───┘

The order is DATA (`table.json`): which event is legal in which step, each step's deadline, which step may say which
kind of line. `advance` is the only writer of a programme's state; an event that arrives out of step is refused and
changes nothing. So the end state is checked only after the executor returned, and an outcome is spoken only after it
exists — by construction, not by a later pass.

What the programme of an action IS comes from its manifest (`programme.of`): whether it asks first, whether it
leaves the machine, how its end state is read. Where a request goes — the conversation, this programme, or a worker —
is `route.destination`. Nothing here imports the turn: the turn, a worker's tool and a test all call the same module.

Stages (`switch.stage`): `shadow` records the programme beside today's path; `own` makes it the path. Both OFF.
"""
from __future__ import annotations

from .state import ENDS, FIRST, LAST, STEPS, Move, advance, due, new, needs_consent, say

__all__ = ["ENDS", "FIRST", "LAST", "STEPS", "Move", "advance", "due", "new", "needs_consent", "say"]

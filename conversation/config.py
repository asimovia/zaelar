"""Every threshold of the conversation manager, with its reason beside it. Frozen; no environment read here.

A threshold is a rule with readers, not a tuning: the adapter that builds the manager may pass a per-operator
`Config` (the rules table), and P4/F1 set the values marked «measured in F0/P4» against the frozen decision rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # ── the ear ──
    #: the longest the ear waits after the voice falls for the provider's end of turn, with full coverage. Above the
    #: provider's timeout path (1.56–1.71 s after the last word, adapter doc A5), under the 2.5 s of D2.
    close_cap_ms: int = 2500
    #: more patience after we asked for something that is said slowly (a number, a date, a spelling) — keyed by the
    #: hint the turn declared, never by the words said.
    patience_ms: dict = field(default_factory=lambda: {"number": 1200, "date": 1000, "spelled": 1500})
    #: the provider sends a watermark every ~240 ms even in silence (A2); four missed beats is a stalled stream (A6).
    stall_ms: int = 1000
    # ── the inbox ──
    #: typed messages sent within this window travel in one batch (the 0.35 s debounce, moved from the ear: PA-4).
    collect_ms: int = 350
    #: a text waits at most this long behind an open voice intervention that began earlier (today's 8 s cap).
    cross_channel_hold_ms: int = 8000
    #: what must be told is never deferred past this; then it is told whatever the state.
    must_tell_max_defer_ms: int = 120_000
    #: progress updates of one task coalesce over this window.
    progress_coalesce_ms: int = 10_000
    #: a to-tell item expires after this if never told (it is reported, never silently lost).
    to_tell_expiry_ms: int = 30 * 60_000
    # ── the gateway ──
    #: extra wait without onset on the initiating device before an ACTION seals (D2's «0.3–0.7 s», PA-3). 0 in the
    #: core; F0/P4 set it.
    action_seal_grace_ms: int = 0
    #: a confirmation handle lives this long after it was presented.
    handle_ttl_ms: int = 120_000
    # ── the manager ──
    #: every accepted request ends (answered, handed off, silent, recovered) within this budget, or is closed
    #: `stalled` by the sweep (I9).
    liveness_ms: int = 30_000
    #: a port call slower than this is an event (the loop-stall lesson of G1).
    port_budget_ms: int = 500
    #: the model used for the conversation (D6); the adapter passes the live id from the model table.
    model_id: str = ""
    # ── the composer ──
    #: OPEN holds at most this many items; the device's focus is always among them.
    open_budget: int = 8
    #: the last turns of the conversation, literal.
    conversation_turns: int = 12

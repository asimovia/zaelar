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
    #: the same person speaking again on the same device within this window of the batch's last entry, while its run
    #: has not published, stops that run and makes its batch wait for that voice (the continuation travels with it).
    #: Never shorter than the model's first-event deadline: a run can take that long before it publishes. P4 sets it.
    resume_window_ms: int = 20_000
    # ── the inbox ──
    #: typed messages sent within this window travel in one batch (the 0.35 s debounce, moved from the ear: PA-4).
    collect_ms: int = 350
    #: a text waits at most this long behind an open voice intervention that began earlier (today's 8 s cap).
    cross_channel_hold_ms: int = 8000
    #: a control is handled by id at once; one accepted and still unaccounted after this (its handler never ran or
    #: raised) is closed by the sweep with a visible outcome (I6).
    control_bound_ms: int = 5000
    # ── the manager ──
    #: every accepted request ends (answered, handed off, silent, recovered) within this budget, or is closed
    #: `stalled` by the sweep (I9).
    liveness_ms: int = 30_000
    #: a port call slower than this is an event (the loop-stall lesson of G1).
    port_budget_ms: int = 500
    #: deadlines of the ports (wall clock): the model's first event and each next one, a tool, the mouth's order,
    #: a memory read. Past them the call is abandoned and the run recovers visibly (I9).
    model_first_ms: int = 20_000
    model_gap_ms: int = 10_000
    tool_ms: int = 15_000
    mouth_ms: int = 3_000
    memory_ms: int = 1_500
    #: a line we said with no `SayEnded` after this (plus ~80 ms a character) ended «unknown»: acks get lost (B4 of
    #: the audit), and the manager never waits on one forever.
    say_end_ms: int = 20_000
    #: what is done — an accounted envelope, an ended line, a final item or intervention — leaves the live tables
    #: after this, so the sweep's cost follows what is in course, not the account's history (NM2); the newest
    #: `conversation_turns` turns always stay. Checked once a `prune_every_ms`.
    retain_ms: int = 10 * 60_000
    prune_every_ms: int = 60_000
    #: a run may call the model at most this many times (tool results fed back between calls).
    max_steps: int = 6
    #: evidence a tool returned stays valid for a numeric claim of a LATER run this long (D9).
    evidence_ttl_ms: int = 10 * 60_000
    #: the model used for the conversation (D6); the adapter passes the live id from the model table.
    model_id: str = ""
    # ── the composer ──
    #: OPEN holds at most this many items, newest first; the rest are counted.
    open_budget: int = 8
    #: the last turns of the conversation, literal.
    conversation_turns: int = 12

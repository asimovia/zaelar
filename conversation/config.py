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
    #: provider's timeout path (1.56–1.71 s after the last word, adapter doc A5), under 2.5 s.
    close_cap_ms: int = 2500
    #: more patience after we asked for something that is said slowly (a number, a date, a spelling) — keyed by the
    #: hint the turn declared, never by the words said.
    patience_ms: dict = field(default_factory=lambda: {"number": 1200, "date": 1000, "spelled": 1500})
    #: the provider sends a watermark every ~240 ms even in silence (adapter doc A2); four missed beats is a stalled stream (adapter doc A6).
    stall_ms: int = 1000
    #: the same person speaking again on a device that contributed to the batch, within this window of the last entry
    #: there, while its run has not published, stops that run and makes its batch wait for that voice (the
    #: continuation travels with it). The hold's bound below rules inside it: past `resume_hold_max_ms` from the batch's
    #: last close no voice holds anything, whatever this window says. Never shorter than the model's first-event
    #: deadline. P4 sets both.
    resume_window_ms: int = 20_000
    #: a batch waits for such a resumed voice at most this long from the close of its last entry, and words do not
    #: reset it — the same sense and value as `cross_channel_hold_ms`: nobody waits behind a voice longer. Past it the
    #: batch runs as it is and the open voice stays its own intervention (a TV that never stops cannot hold it forever).
    resume_hold_max_ms: int = 8000
    #: a voice born at a close with the voice still up, that falls before this with no word, was the tail of the
    #: voice that closed: discarded at once, not at the cap (the provider's end lands a few ms before the fall).
    min_voice_ms: int = 250
    lost_voice_ms: int = 1000        # his voice this long, cut by a stall or a hole with no word heard: lost, and told
    #: an intervention is at most this long, from its onset, never reset by words: past it what was heard is delivered
    #: incomplete (`too_long`) and, with the voice still up, the next one starts.
    intervention_max_ms: int = 30_000
    #: half a thought is not answered (v3.1 §1.6 ter, measured on 66 sessions: after an end WITHOUT a sentence mark he
    #: goes on 93 % of the time, 86 % within 1.5 s; after one WITH a mark, 60 %): a batch with a voice entry closed with
    #: no mark is not eligible before this from its close, and is not published before `nonterminal_grace_ms`…
    nonterminal_start_ms: int = 1500
    nonterminal_grace_ms: int = 5000
    #: …and one closed with a mark (or unknown) runs at once but is not published before this. With several voice
    #: entries the latest grace rules; a text has none. 0 publishes at once. The host sets all three as thresholds.
    terminal_grace_ms: int = 3000
    #: §1.6 quater: when the model says, with its order, whether the thought is answerable, its reading replaces the
    #: two graces above — not before `complete_grace_ms` from the last voice close if it is, not before
    #: `incomplete_grace_ms` if something seems missing. The mark still decides when the run starts. Thresholds.
    complete_grace_ms: int = 1000
    incomplete_grace_ms: int = 6000
    #: a barge-in that ended with no word (no voice, a noise) resumes the line it cut, once, from the last sentence
    #: heard — if it ends within this of the cut and no entry with words came in between.
    resume_cut_within_ms: int = 4000
    # ── the inbox ──
    #: typed messages sent within this window travel in one batch (the 0.35 s debounce: batching belongs to the inbox, not the ear).
    collect_ms: int = 0              # two texts closer than this are one batch; 0: each its own (B7i, measured)
    #: a text waits at most this long behind an open voice intervention that began earlier (today's 8 s cap).
    cross_channel_hold_ms: int = 8000
    #: a control is handled by id at once; one accepted and still unaccounted after this (its handler never ran or
    #: raised) is closed by the sweep with a visible outcome (I6).
    control_bound_ms: int = 5000
    # ── the manager ──
    #: every accepted request ends (answered, handed off, silent, recovered) within this budget, or is closed
    #: `stalled` by the sweep (I9).
    liveness_ms: int = 30_000
    #: a port call slower than its budget is an event (`conv_run/port_slow`; the loop-stall lesson of G1): each port its
    #: own — a store transaction is slow at 50 ms, a model's first event at 2 s — and `port_budget_ms` for any other.
    port_budget_ms: int = 500
    model_budget_ms: int = 2000
    tools_budget_ms: int = 3000
    memory_budget_ms: int = 300
    store_budget_ms: int = 50
    mouth_budget_ms: int = 500
    #: deadlines of the ports (wall clock): the model's first event and each next one, a tool, the mouth's order,
    #: a memory read. Past them the call is abandoned and the run recovers visibly (I9).
    model_first_ms: int = 20_000
    model_gap_ms: int = 10_000
    tool_ms: int = 15_000
    mouth_ms: int = 3_000
    memory_ms: int = 1_500
    #: a line we said with no `SayEnded` after this (plus ~80 ms a character) ended «unknown»: acks get lost, and the
    #: manager never waits on one forever.
    say_end_ms: int = 20_000
    #: a run may call the model at most this many times (tool results fed back between calls).
    #: A searched turn takes 2–3 (a read, maybe another, the order) and the repairs one each; a run that reaches the cap
    #: still ends in a line he hears (`mute_lines`), never in a silent failure.
    max_steps: int = 6
    #: §1.10 bis: a DERIVED figure (counted or averaged from what a read of this run returned) may be said, citing
    #: that evidence — the door closes with this at False; and a reply with derived figures spends its one repair
    #: round to say what they rest on only with the second at True (off: the judge of the text suite measures it).
    derived_claims_open: bool = True
    derived_claims_repair: bool = False
    #: U44: a text that follows a voice of his that was lost (discarded, or ended incomplete) within this window
    #: carries the fact in its prompt — how long ago and why.
    voice_lost_window_ms: int = 60_000
    #: evidence a tool returned stays valid for a numeric claim of a LATER run this long.
    evidence_ttl_ms: int = 10 * 60_000
    #: the model used for the conversation; the adapter passes the live id from the model table.
    model_id: str = ""
    # ── the composer ──
    #: OPEN holds at most this many items, newest first; the rest are counted.
    open_budget: int = 8
    #: the last turns of the conversation, literal.
    conversation_turns: int = 12
    #: a silence longer than this ends a session: the turns before it reach the model marked as an earlier session,
    #: with their age — history, never what is being answered now.
    session_gap_ms: int = 30 * 60_000

    def misordered(self) -> list[str]:
        """The graces only bound each other in this order (§1.6 quater: the model's reading never waits longer than
        `incomplete_grace_ms` nor shorter than `complete_grace_ms`, and the hold for his voice outlasts them all):
        complete ≤ terminal ≤ nonterminal ≤ incomplete ≤ resume_hold_max. The pairs out of order, by name — the host
        refuses a configuration that has any."""
        chain = ("complete_grace_ms", "terminal_grace_ms", "nonterminal_grace_ms", "incomplete_grace_ms",
                 "resume_hold_max_ms")
        return [f"{a} > {b}" for a, b in zip(chain, chain[1:]) if getattr(self, a) > getattr(self, b)]

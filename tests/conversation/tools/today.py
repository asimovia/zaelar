"""What today's observer events MEAN, in one table: the vocabulary the F0 baseline and the P2 converter read.

The engine of today labels its events for a human (an emoji and a phrase), so a reader of an archive has to match
those labels. That matching lives here and only here, as a test tool: it reads the record of the path being
replaced, it decides nothing in the product. Every row says what it stands for. When a label changes in the engine,
this table is the one place to update, and `test_baseline_counts_a_synthetic_archive.py` names the row that broke.

`classify(ev)` returns one signal name (or None). Rows are tried in order; the first that matches wins.
"""
from __future__ import annotations

import re

from tests.conversation.tools.archive import Event

# (signal, kind, predicate over the event) — the predicate reads payload keys first, label text only where the
# engine of today put the meaning nowhere else.
_ROWS: tuple[tuple[str, str, object], ...] = (
    # the ear
    ("eager", "vad", lambda e: e.payload.get("detector") == "stt-eager"),
    ("held", "vad", lambda e: bool(e.payload.get("why")) or "RETENIDO" in e.label),
    ("vad_on", "vad", lambda e: e.payload.get("edge") == "on"),
    ("vad_off", "vad", lambda e: e.payload.get("edge") == "off"),
    ("user_interim", "interim", lambda e: True),
    ("typed", "transcript", lambda e: "chat" in e.label),
    ("user_final", "transcript", lambda e: e.payload.get("role", "user") == "user"),
    ("agent_line", "transcript", lambda e: True),
    # the turn and what decides around it
    ("prompt", "brain", lambda e: e.label.endswith(": prompt") and "Nucleo" in e.label),
    ("turn_cancelled", "brain", lambda e: "cut_after_ms" in e.payload),
    ("fragment_dropped", "brain", lambda e: "dropped_reply" in e.payload or "descartad" in e.label),
    ("held", "brain", lambda e: e.label.startswith("⏸")),
    ("decider", "brain", lambda e: e.label.startswith("jev ")),
    ("loop_nudge", "brain", lambda e: "break-loop" in e.label),
    ("unreadable_ask", "brain", lambda e: "readable" in e.payload or "unreadable" in e.label),
    ("forced_source", "brain", lambda e: e.label.startswith("📖")),
    ("forced_source", "rail", lambda e: True),
    # the mouth and the control lane
    ("stop_attended", "ambient", lambda e: e.payload.get("reason") == "hard_interrupt"),
    ("agent_speaking", "bot_speech", lambda e: e.payload.get("speaking") is True or e.label == "speaking"),
    ("agent_idle", "bot_speech", lambda e: e.payload.get("speaking") is False or e.label == "idle"),
    ("first_audio", "perf", lambda e: "onset_ms" in e.payload or "primer audio" in e.label),
    # the host
    ("loop_stall", "homeostasis", lambda e: "lag_s" in e.payload),
)

_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")


def classify(ev: Event) -> str | None:
    for signal, kind, pred in _ROWS:
        if ev.kind == kind and pred(ev):
            return signal
    return None


def first_audio_ms(ev: Event) -> float | None:
    """The speech-end → first-audio figure of a `first_audio` event: a payload field when present, else the first
    number of its label (today's engine writes it only there)."""
    for key in ("ms", "first_audio_ms", "ttfa_ms"):
        if isinstance(ev.payload.get(key), (int, float)):
            return float(ev.payload[key])
    m = _NUMBER.search(ev.label)
    return float(m.group(1)) if m else None


def stall_ms(ev: Event) -> float | None:
    lag = ev.payload.get("lag_s")
    return float(lag) * 1000.0 if isinstance(lag, (int, float)) else None


SIGNALS = tuple(dict.fromkeys(r[0] for r in _ROWS))

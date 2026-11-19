"""What the ear is fed (§5.2). An adapter builds these from the speech provider, the local VAD, the clients and the
safety guards; a replay builds them from a recorded session. All times are WALL milliseconds — the adapter maps the
provider's audio time once per stream (adapter doc A9).

The ear has no clock of its own: time passes for it only through the signals, and `Tick` is the signal that says
«it is now t» when nothing else arrives (caps and stalls are judged on it).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WordSpan:
    """A partial or final hypothesis of one provider turn (`seq`); a higher `revision` of the same seq REPLACES it."""
    stream: str
    seq: int
    revision: int
    final: bool
    words: tuple[tuple[str, int, int, float], ...]   # (text, t0_ms, t1_ms, conf)
    window: tuple[int, int]                           # the audio this hypothesis covers


@dataclass(frozen=True)
class Watermark:
    """«The provider has processed the audio through here» — it advances in silence too (adapter doc A2)."""
    stream: str
    processed_through_ms: int


@dataclass(frozen=True)
class VadEdge:
    endpoint: str
    edge: str          # "rise" | "fall"
    t_ms: int
    echo_safe: bool = True   # False while our own voice may be what the microphone hears


@dataclass(frozen=True)
class EotHint:
    stream: str
    source: str        # "flux" | "smart_turn" | "rules"
    kind: str          # "eager" | "resumed" | "end"
    prob: float | None
    t_ms: int


@dataclass(frozen=True)
class PlaybackState:
    endpoint: str
    speaking: bool
    t_ms: int


@dataclass(frozen=True)
class ContextHint:
    """Patience for what we just asked for: a number, a date, a spelling. Declared by the turn, never read off the
    words heard."""
    endpoint: str
    expect: str | None   # "number" | "date" | "spelled" | None


@dataclass(frozen=True)
class TypedSubmit:
    endpoint: str
    client_id: str
    text: str
    t_ms: int


@dataclass(frozen=True)
class Discard:
    """A safety guard outside the ear threw speech away (echo, the voice lock, a blocked mic, not addressed to us)."""
    endpoint: str
    text: str
    reason: str        # "echo" | "voice_lock" | "mic_blocked" | "not_addressed"
    t_ms: int


@dataclass(frozen=True)
class Sealed:
    """The ledger sealed this revision (its first effect or publication): later voice amends, never reopens."""
    intervention_id: str
    revision: int


@dataclass(frozen=True)
class Finished:
    """The request of this intervention reached a final state (answered, handed off, silent, recovered, failed): its
    revisions are final for the ear — later voice opens a NEW intervention, never a revision of this one (I3, N1)."""
    intervention_id: str
    revision: int


@dataclass(frozen=True)
class Tick:
    t_ms: int


@dataclass(frozen=True)
class Onset:
    """Out of the ear, on the CONTROL lane (never through the inbox): the person started speaking on this device."""
    endpoint: str
    t_ms: int
    intervention_id: str


Signal = (WordSpan | Watermark | VadEdge | EotHint | PlaybackState | ContextHint | TypedSubmit | Discard | Sealed
          | Finished | Tick)

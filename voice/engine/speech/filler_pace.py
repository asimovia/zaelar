"""voice/engine/speech/filler_pace.py — is the engine answering fast right now? The cover's memory of recent turns (V2-716).

The operator's second rule, 2026-09-17: when the replies' latencies are falling under a second, and that is the
average of the last few phrases, the cover is not needed; when the last one, two or three go beyond a second, the
flag comes back on.

The per-turn race (`filler_audio.delay_ms`) already silences a fast turn, so this does NOT change what the operator
hears on a turn that beats the deadline. What it removes is the other half of arming, which the race cannot: the
`[SISTEMA]` note `arm()` appends to the last user message, promising the model a cover phrase to continue. On an
engine that is answering in well under a second that note is pure prompt noise steering replies into «Got it — …»
continuations of a phrase that will never sound.

Re-arming is deliberately TWITCHY in the slow direction: one recent turn over the deadline brings the cover back. A
missing cover on a slow turn is dead air, which is the failure the cover exists to prevent; an extra cover on a fast
turn is one short word. Asymmetric on purpose.

Split out of `filler_audio.py` (2026-11-12, past its size ceiling): the part that is pure memory of earlier turns.
"""
from __future__ import annotations

_RECENT_TTFT: list[int] = []
_FAST_WINDOW = 3          # how many recent turns must ALL be fast before arming stops
_state = {"stranded": False}   # V2-716: the last generation sounded a cover and the model answered nothing


def note_latency(ttft_ms) -> None:
    """One turn's measured time-to-first-spoken-token. Called by the voice provider once the turn's own
    metrics exist. `None` — a turn that produced no speakable text at all — is NOT a fast turn and is not a
    slow one either: it is no evidence, and recording it either way would be a lie the next turn acts on."""
    if not isinstance(ttft_ms, (int, float)) or not 1 <= ttft_ms < float("inf"):
        return
    _RECENT_TTFT.append(int(ttft_ms))
    del _RECENT_TTFT[:-8]


def _note_stranded(value: bool) -> None:
    _state["stranded"] = bool(value)


def stranded() -> bool:
    """The previous generation's cover was the ONLY thing the operator heard on that turn."""
    return _state["stranded"]


def answering_fast(deadline_ms: int) -> bool:
    """True when the last `_FAST_WINDOW` measured turns ALL beat the cover deadline — the engine is fast
    enough right now that the cover has nothing to cover. False until that much evidence exists, so a fresh
    process, a reconnect or a model swap arms normally rather than guessing."""
    if deadline_ms <= 0 or len(_RECENT_TTFT) < _FAST_WINDOW:
        return False
    return all(v < deadline_ms for v in _RECENT_TTFT[-_FAST_WINDOW:])

"""Small builders for ear signals in tests: words are tokens (`w0001`), times are ms from 0."""
from __future__ import annotations

from conversation import envelopes as E
from conversation.ear import signals as S
from conversation.types import EnvelopeKind, IvState

D = "d1"


def words(*toks: str, t0: int = 0, step: int = 200) -> tuple:
    return tuple((tok, t0 + i * step, t0 + (i + 1) * step - 20, 1.0) for i, tok in enumerate(toks))


def span(seq: int, rev: int, final: bool, ws: tuple, stream: str = D) -> S.WordSpan:
    end = ws[-1][2] if ws else 0
    start = ws[0][1] if ws else 0
    return S.WordSpan(stream, seq, rev, final, ws, (start, end))


def beats(t0: int, t1: int, step: int = 240, stream: str = D) -> list:
    """The provider's watermark, every ~240 ms, in silence too (adapter doc A2)."""
    return [S.Watermark(stream, t) for t in range(t0, t1 + 1, step)]


def feed(ear, *sigs) -> list:
    out = []
    for s in sigs:
        for one in (s if isinstance(s, list) else [s]):
            out.extend(ear.feed(one))
    return out


def utterances(out: list) -> list[E.Envelope]:
    """The utterances that closed whole."""
    return [e for e in out if isinstance(e, E.Envelope) and e.kind is EnvelopeKind.USER_UTTERANCE
            and e.body.coverage == "full"]


def states(out: list) -> list[tuple[str, str]]:
    """(state, intervention) the ear reported, in order: open (its onset), incomplete (an utterance without its end),
    discarded. A closed one is an utterance (`utterances`); tentative and extended are events, not outputs."""
    seen = []
    for e in out:
        if isinstance(e, S.Onset):
            seen.append((OPEN, e.intervention_id))
        elif isinstance(e, S.VoiceDiscarded):
            seen.append((DISCARDED, e.intervention_id))
        elif isinstance(e, E.Envelope) and e.kind is EnvelopeKind.USER_UTTERANCE and e.body.coverage != "full":
            seen.append((INCOMPLETE, e.body.intervention_id))
    return seen


def onsets(out: list) -> list[S.Onset]:
    return [e for e in out if isinstance(e, S.Onset)]


OPEN, TENTATIVE, INCOMPLETE, DISCARDED = (str(IvState.OPEN), str(IvState.TENTATIVE), str(IvState.INCOMPLETE),
                                          str(IvState.DISCARDED))

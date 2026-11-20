"""The ear: ONE arbiter decides when the person finished an intervention. Pure: no clock, no I/O.

A voice intervention moves open → (tentative ↔ extended) → closed, or → incomplete / discarded. It CLOSES only when
three things hold at once: the provider's end of turn (`EotHint(end)`), full coverage (every provider turn assigned
to it has its final, I2) and the watermark past the voice's last fall — so the last words cannot still be on their
way. Or, past the cap, with full coverage: the cap counts from the voice's fall, or from the provider's end when the
voice never fell, or — with neither — from the last word heard (from the onset if there was none), so an open voice
always ends: with words it closes or is incomplete, without any it is discarded. Never by two detectors agreeing with
each other: an eager hint only makes it TENTATIVE, and a tentative intervention is not delivered to anyone.

Without coverage at the cap, or with a stream that stopped beating (the watermark not advancing while time passes,
adapter doc A6), the intervention is INCOMPLETE: not actionable, the run asks for the end. An intervention also has a
maximum length (`intervention_max_ms`, from its onset, never reset by words): past it, what was heard is delivered
incomplete (`too_long`) — a background that never stops talking cannot keep a turn open.

The ear does not tell speakers apart; it guarantees what happens around another voice. If the voice is still UP when
the provider ends its turn (a rise with no fall since), there is no «caught up»: the intervention closes on the end and
its coverage, and in the same step the next one is born there — the manager sees a voice open on that device right
after the close, which is what the publication hold needs. A rise that comes while an end is pending (the watermark
not yet past the fall) is the same: the person goes on, the next intervention starts at that rise. Words of a later
provider turn — or late words of a turn whose intervention ended — are the open successor's, never the ended one's. A
successor that falls before `min_voice_ms` with no word was no voice: discarded at once, not at the cap.

The intervention is the unit: once it ended, nothing reopens it. Voice that follows is ANOTHER intervention, which
`amends` the previous one when we have not spoken since; the manager decides whether the two travel together.

Out: the person's entries for the inbox (`user.utterance` — whole, or incomplete with what was heard — and
`user.text`), and two facts for the manager: `Onset` (a voice opened: the control lane) and `VoiceDiscarded`.
"""
from __future__ import annotations

from dataclasses import dataclass

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import signals as S
from conversation.ear.spans import Spans
from conversation.ear.typed import submit
from conversation.telemetry import Emitter
from conversation.types import Channel, Coverage, EnvelopeKind, Ids, IvState

OPEN_STATES = (IvState.OPEN, IvState.TENTATIVE)
ENDED_STATES = (IvState.CLOSED, IvState.INCOMPLETE)


@dataclass
class _Voice:
    endpoint: str
    iv: str | None = None
    state: IvState | None = None
    onset_ms: int = 0
    eot_end_ms: int | None = None
    eot_prob: float | None = None
    fall_ms: int | None = None
    watermark_ms: int | None = None
    expect: str | None = None
    amends: str | None = None
    previous: str | None = None             # the last intervention that ended with words, on this device
    agent_spoke: bool = False               # we spoke after `previous` ended: what follows is new, not its amendment
    closed_ms: int = 0
    last_word_ms: int | None = None
    up: bool = False                        # a rise with no fall since: the voice is still sounding
    successor: bool = False                 # born at a close with the voice still up (it may be no voice at all)


class Ear:
    def __init__(self, account: str, config: Config, emitter: Emitter, ids: Ids) -> None:
        self.account, self.cfg, self.em, self.ids = account, config, emitter, ids
        self.spans = Spans()
        self._voices: dict[str, _Voice] = {}
        self._now = 0

    # ── in ──────────────────────────────────────────────────────────────────────────────────────────────────────

    def feed(self, sig: S.Signal) -> list:
        out: list = []
        handler = getattr(self, f"_on_{type(sig).__name__}")
        handler(sig, out)
        return out

    def _v(self, endpoint: str) -> _Voice:
        return self._voices.setdefault(endpoint, _Voice(endpoint))

    def _time(self, t: int) -> int:
        self._now = max(self._now, t)
        return self._now

    def _on_Tick(self, sig: S.Tick, out: list) -> None:
        t = self._time(sig.t_ms)
        for v in self._voices.values():
            self._judge(v, t, out)

    def _on_Watermark(self, sig: S.Watermark, out: list) -> None:
        v = self._v(sig.stream)
        v.watermark_ms = max(v.watermark_ms or 0, sig.processed_through_ms)
        self._judge(v, self._time(sig.processed_through_ms), out)

    def _on_WordSpan(self, sig: S.WordSpan, out: list) -> None:
        v = self._v(sig.stream)
        t = self._time(sig.window[1])
        v.watermark_ms = max(v.watermark_ms or 0, sig.window[1])
        owner = self.spans.owner(sig.stream, sig.seq)
        if owner is None and sig.words:
            self._start(v, sig.words[0][1], out)
        elif owner is not None and (owner != v.iv or v.state not in OPEN_STATES) and sig.words:
            # words of a provider turn whose intervention already ended: new voice, never a revision of the ended one —
            # they go to the open intervention of this device (a successor born at the close), or start one
            self._start(v, t, out)
            self.spans.reassign_seq(sig.stream, sig.seq, owner, v.iv)
            owner = v.iv
        target = owner or v.iv
        if target is None:
            return
        grew = self.spans.add(sig.stream, sig.seq, sig.revision, sig.final, sig.words, target)
        if grew and target == v.iv:
            v.last_word_ms = t
            if v.state is IvState.TENTATIVE:
                self._state(v, IvState.OPEN, "extended", t, out)
        self._judge(v, t, out)

    def _on_VadEdge(self, sig: S.VadEdge, out: list) -> None:
        v = self._v(sig.endpoint)
        t = self._time(sig.t_ms)
        if sig.edge == "fall":
            v.fall_ms, v.up = sig.t_ms, False
            if (v.successor and v.state in OPEN_STATES and not self.spans.words(v.iv)
                    and sig.t_ms - v.onset_ms < self.cfg.min_voice_ms):
                self._discard_empty(v, t, out, reason="no_voice")     # born at a close, and it was the tail of it
                return
            self._judge(v, t, out)
        elif sig.echo_safe:
            v.fall_ms, v.up = None, True
            self._start(v, sig.t_ms, out)
            self._judge(v, t, out, rise=sig.t_ms)   # an end pending, the voice up again: close; the next one starts AT it

    def _on_EotHint(self, sig: S.EotHint, out: list) -> None:
        v = self._v(sig.stream)
        t = self._time(sig.t_ms)
        if v.state not in OPEN_STATES:
            return
        v.eot_prob = sig.prob
        if sig.kind == "eager" and v.state is IvState.OPEN:
            self._state(v, IvState.TENTATIVE, "tentative", t, out)
        elif sig.kind == "resumed" and v.state is IvState.TENTATIVE:
            v.eot_end_ms = None
            self._state(v, IvState.OPEN, "extended", t, out)
        elif sig.kind == "end":
            v.eot_end_ms = t
        self._judge(v, t, out)

    def _on_PlaybackState(self, sig: S.PlaybackState, out: list) -> None:
        if sig.speaking:
            self._v(sig.endpoint).agent_spoke = True

    def _on_ContextHint(self, sig: S.ContextHint, out: list) -> None:
        self._v(sig.endpoint).expect = sig.expect

    def _on_TypedSubmit(self, sig: S.TypedSubmit, out: list) -> None:
        out.append(submit(self, sig, self._time(sig.t_ms)))

    def _on_Discard(self, sig: S.Discard, out: list) -> None:
        v = self._v(sig.endpoint)
        t = self._time(sig.t_ms)
        refs = {"endpoint": sig.endpoint, "channel": "voice"}
        if v.state in OPEN_STATES:
            refs.update(iv=v.iv)
            v.state = IvState.DISCARDED
            out.append(S.VoiceDiscarded(v.endpoint, v.iv, t))
        self.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "guard", "ref": sig.reason}, refs=refs,
                     trace=v.iv if refs.get("iv") else f"guard:{sig.endpoint}:{t}", text=sig.text, reason=sig.reason)

    # ── transitions ─────────────────────────────────────────────────────────────────────────────────────────────

    def _start(self, v: _Voice, t: int, out: list, *, successor: bool = False) -> None:
        """Voice begins: a NEW intervention, unless one is already open on this device."""
        if v.state in OPEN_STATES:
            return
        v.amends = v.previous if (v.previous and not v.agent_spoke) else None
        v.agent_spoke = False
        v.iv, v.state, v.onset_ms, v.successor = self.ids.new("iv"), IvState.OPEN, t, successor
        v.eot_end_ms = v.eot_prob = v.fall_ms = v.last_word_ms = None   # nothing of the previous one is this one's
        out.append(S.Onset(v.endpoint, t, v.iv))
        self.em.emit("conv_ear", "onset", owner="ear", cause={"kind": "voice"}, refs=self._refs(v), t_onset_ms=t)
        self.em.emit("conv_ear", "opened", owner="ear", cause={"kind": "voice"}, refs=self._refs(v),
                     amends=v.amends)

    def _state(self, v: _Voice, state: IvState, label: str, t: int, out: list) -> None:
        v.state = state
        self.em.emit("conv_ear", label, owner="ear", cause={"kind": "provider"}, refs=self._refs(v),
                     eot_prob=v.eot_prob)

    def _judge(self, v: _Voice, t: int, out: list, rise: int | None = None) -> None:
        if v.state not in OPEN_STATES:
            return
        covered = self.spans.covered(v.iv)
        # a rise clears the fall: with the voice still up the end closes on its coverage (no watermark to wait for),
        # and the next intervention starts here (below)
        caught_up = v.fall_ms is None or (v.watermark_ms or 0) >= v.fall_ms
        cap = self.cfg.close_cap_ms + self.cfg.patience_ms.get(v.expect or "", 0)
        # the cap counts from the fall, else from the provider's end, else from the last word (else the onset)
        anchor = next(x for x in (v.fall_ms, v.eot_end_ms, v.last_word_ms, v.onset_ms) if x is not None)
        if v.eot_end_ms is not None and covered and caught_up:
            self._close(v, t, "eot", out)
            if v.up:                            # born where the voice rose again, or here if it never fell
                self._start(v, t if rise is None else rise, out, successor=rise is None)
        elif t - v.onset_ms >= self.cfg.intervention_max_ms and self.spans.words(v.iv):
            self._incomplete(v, t, "too_long", out)          # never reset by words: a background cannot hold it open
            if v.up:
                self._start(v, t, out, successor=True)
        elif t - anchor >= cap:
            if not self.spans.words(v.iv):
                self._discard_empty(v, t, out)
            elif covered:
                self._close(v, t, "cap", out)
            else:
                self._incomplete(v, t, "no_final", out)
        elif v.watermark_ms is not None and t - max(v.watermark_ms, v.onset_ms) >= self.cfg.stall_ms:
            # a stream that stopped beating — measured from this voice's onset at the earliest: a watermark left
            # from before it (the stream idle between interventions) is no stall of this one. No words: nothing to end.
            if self.spans.words(v.iv):
                self._incomplete(v, t, "stalled", out)
            else:
                self._discard_empty(v, t, out)

    def _utterance(self, v: _Voice, t: int, coverage: Coverage, reason: str | None = None) -> E.Envelope:
        words = self.spans.words(v.iv)
        body = E.UtteranceBody(v.iv, " ".join(w[0] for w in words), tuple(E.Span(*w) for w in words),
                               coverage=coverage, amends=v.amends, reason=reason)
        return E.make(EnvelopeKind.USER_UTTERANCE, body, producer=f"ear:{v.endpoint}",
                      producer_id=f"{v.iv}:{coverage}", account=self.account, onset_ms=v.onset_ms, sealed_ms=t,
                      channel=Channel.VOICE, endpoint=v.endpoint, refs=E.Refs(intervention_id=v.iv))

    def _close(self, v: _Voice, t: int, by: str, out: list) -> None:
        v.state, v.closed_ms, v.previous = IvState.CLOSED, t, v.iv
        words = self.spans.words(v.iv)
        out.append(self._utterance(v, t, Coverage.FULL))
        last = words[-1][2] if words else t
        self.em.emit("conv_ear", "closed", owner="ear", cause={"kind": "provider" if by == "eot" else "cap"},
                     refs=self._refs(v), closed_by=by, words=len(words), t0_ms=v.onset_ms, t1_ms=last,
                     watermark_ms=v.watermark_ms, vad_fall_ms=v.fall_ms, eot_prob=v.eot_prob,
                     wait_ms=t - (v.fall_ms or last))

    def _discard_empty(self, v: _Voice, t: int, out: list, reason: str = "no_words") -> None:
        """Voice rose and fell and no word came: nothing to answer, and the discard is an event (I4)."""
        v.state = IvState.DISCARDED
        out.append(S.VoiceDiscarded(v.endpoint, v.iv, t))
        self.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "cap" if reason == "no_words" else "voice"},
                     refs=self._refs(v), text="", reason=reason)

    def _incomplete(self, v: _Voice, t: int, reason: str, out: list) -> None:
        v.state, v.closed_ms, v.previous = IvState.INCOMPLETE, t, v.iv
        text = " ".join(w[0] for w in self.spans.words(v.iv))
        out.append(self._utterance(v, t, Coverage.INCOMPLETE, reason))
        self.em.emit("conv_ear", "incomplete", owner="ear", cause={"kind": "cap" if reason in ("no_final", "too_long")
                                                                   else "stall"},
                     refs=self._refs(v), text=text, reason=reason, watermark_ms=v.watermark_ms)

    # ── out ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def _refs(self, v: _Voice) -> dict:
        return {"iv": v.iv, "endpoint": v.endpoint, "channel": "voice"}

    def open_ids(self) -> set[str]:
        """The interventions this ear is still hearing (open or tentative)."""
        return {v.iv for v in self._voices.values() if v.state in OPEN_STATES and v.iv}

    def open_intervention(self, endpoint: str | None = None) -> tuple[str, int] | None:
        """(intervention, onset) of an open voice intervention — on that endpoint, or on any."""
        for v in self._voices.values():
            if v.state in OPEN_STATES and (endpoint is None or v.endpoint == endpoint):
                return v.iv, v.onset_ms
        return None

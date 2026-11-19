"""The ear: ONE arbiter decides when the person finished an intervention (§6.1, D1). Pure: no clock, no I/O.

A voice intervention moves open → (tentative ↔ extended) → closed, or → incomplete / discarded. It CLOSES only when
three things hold at once: the provider's end of turn (`EotHint(end)`), full coverage (every provider turn assigned
to it has its final, I2) and the watermark past the voice's last fall — so the last words cannot still be on their
way. Or, past the cap, with full coverage: the cap counts from the voice's fall, or from the provider's end when the
voice never fell, or — with neither — from the last word heard (from the onset if there was none), so an open voice
always ends: with words it closes or is incomplete, without any it is discarded. Never by two detectors agreeing with
each other (A6): an eager hint only makes it TENTATIVE, and a tentative intervention is not delivered to anyone.

Without coverage at the cap, or with a stream that stopped beating (the watermark not advancing while time passes,
adapter doc A6), the intervention is INCOMPLETE: not actionable, the run asks for the end.

The intervention is the unit: once it ended, nothing reopens it. Voice that follows is ANOTHER intervention, which
`amends` the previous one when we have not spoken since; the manager decides whether the two travel together.

Out: envelopes for the inbox (`intervention.state`, `user.utterance`, `user.text`) and `Onset` for the control lane.
"""
from __future__ import annotations

from dataclasses import dataclass

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import signals as S
from conversation.ear.spans import Spans
from conversation.ear.typed import submit
from conversation.telemetry import Emitter
from conversation.types import Channel, EnvelopeKind, Ids, IvState

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
        elif owner is not None and owner == v.iv and v.state in ENDED_STATES and sig.words:
            ended = v.iv                          # the end of a provider turn whose intervention already ended:
            self._start(v, t, out)                # it is new voice, never a revision of the ended one
            self.spans.reassign_seq(sig.stream, sig.seq, ended, v.iv)
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
            v.fall_ms = sig.t_ms
            self._judge(v, t, out)
        elif sig.echo_safe:
            v.fall_ms = None
            self._start(v, sig.t_ms, out)

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
            out.append(self._env_state(v, IvState.DISCARDED, t, text=sig.text, reason=sig.reason))
        self.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "guard", "ref": sig.reason}, refs=refs,
                     text=sig.text, reason=sig.reason)

    # ── transitions ─────────────────────────────────────────────────────────────────────────────────────────────

    def _start(self, v: _Voice, t: int, out: list) -> None:
        """Voice begins: a NEW intervention, unless one is already open on this device."""
        if v.state in OPEN_STATES:
            return
        v.amends = v.previous if (v.previous and not v.agent_spoke) else None
        v.agent_spoke = False
        v.iv, v.state, v.onset_ms = self.ids.new("iv"), IvState.OPEN, t
        v.eot_end_ms = v.eot_prob = v.fall_ms = v.last_word_ms = None   # nothing of the previous one is this one's
        out.append(S.Onset(v.endpoint, t, v.iv))
        out.append(self._env_state(v, IvState.OPEN, t))
        self.em.emit("conv_ear", "onset", owner="ear", cause={"kind": "voice"}, refs=self._refs(v), t_onset_ms=t)
        self.em.emit("conv_ear", "opened", owner="ear", cause={"kind": "voice"}, refs=self._refs(v),
                     amends=v.amends)

    def _state(self, v: _Voice, state: IvState, label: str, t: int, out: list) -> None:
        v.state = state
        out.append(self._env_state(v, state, t))
        self.em.emit("conv_ear", label, owner="ear", cause={"kind": "provider"}, refs=self._refs(v),
                     eot_prob=v.eot_prob)

    def _judge(self, v: _Voice, t: int, out: list) -> None:
        if v.state not in OPEN_STATES:
            return
        covered = self.spans.covered(v.iv)
        caught_up = v.fall_ms is None or (v.watermark_ms or 0) >= v.fall_ms
        cap = self.cfg.close_cap_ms + self.cfg.patience_ms.get(v.expect or "", 0)
        # the cap counts from the fall, else from the provider's end, else from the last word (else the onset)
        anchor = next(x for x in (v.fall_ms, v.eot_end_ms, v.last_word_ms, v.onset_ms) if x is not None)
        if v.eot_end_ms is not None and covered and caught_up:
            self._close(v, t, "eot", out)
        elif t - anchor >= cap:
            if not self.spans.words(v.iv):
                self._discard_empty(v, t, out)
            elif covered:
                self._close(v, t, "cap", out)
            else:
                self._incomplete(v, t, "no_final", out)
        elif v.watermark_ms is not None and t - max(v.watermark_ms, v.onset_ms) >= self.cfg.stall_ms:
            # a stream that stopped beating — measured from this voice's onset at the earliest: a watermark left
            # from before it (the stream idle between interventions) is no stall of this one
            self._incomplete(v, t, "stalled", out)

    def _close(self, v: _Voice, t: int, by: str, out: list) -> None:
        v.state, v.closed_ms, v.previous = IvState.CLOSED, t, v.iv
        words = self.spans.words(v.iv)
        body = E.UtteranceBody(v.iv, " ".join(w[0] for w in words), tuple(E.Span(*w) for w in words),
                               amends=v.amends)
        out.append(E.make(EnvelopeKind.USER_UTTERANCE, body, producer=f"ear:{v.endpoint}",
                          producer_id=f"{v.iv}:closed", account=self.account, onset_ms=v.onset_ms,
                          sealed_ms=t, channel=Channel.VOICE, endpoint=v.endpoint,
                          refs=E.Refs(intervention_id=v.iv)))
        last = words[-1][2] if words else t
        self.em.emit("conv_ear", "closed", owner="ear", cause={"kind": "provider" if by == "eot" else "cap"},
                     refs=self._refs(v), closed_by=by, words=len(words), t0_ms=v.onset_ms, t1_ms=last,
                     watermark_ms=v.watermark_ms, vad_fall_ms=v.fall_ms, eot_prob=v.eot_prob,
                     wait_ms=t - (v.fall_ms or last))

    def _discard_empty(self, v: _Voice, t: int, out: list) -> None:
        """Voice rose and fell and no word came: nothing to answer, and the discard is an event (I4)."""
        v.state = IvState.DISCARDED
        out.append(self._env_state(v, IvState.DISCARDED, t, text="", reason="no_words"))
        self.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "cap"}, refs=self._refs(v), text="",
                     reason="no_words")

    def _incomplete(self, v: _Voice, t: int, reason: str, out: list) -> None:
        v.state, v.closed_ms, v.previous = IvState.INCOMPLETE, t, v.iv
        text = " ".join(w[0] for w in self.spans.words(v.iv))
        out.append(self._env_state(v, IvState.INCOMPLETE, t, text=text, reason=reason))
        self.em.emit("conv_ear", "incomplete", owner="ear", cause={"kind": "cap" if reason == "no_final"
                                                                   else "stall"},
                     refs=self._refs(v), text=text, reason=reason, watermark_ms=v.watermark_ms)

    # ── out ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def _refs(self, v: _Voice) -> dict:
        return {"iv": v.iv, "endpoint": v.endpoint, "channel": "voice"}

    def _env_state(self, v: _Voice, state: IvState, t: int, *, text: str | None = None,
                   reason: str | None = None) -> E.Envelope:
        body = E.InterventionStateBody(v.iv, state, text, reason)
        return E.make(EnvelopeKind.INTERVENTION_STATE, body, producer=f"ear:{v.endpoint}",
                      producer_id=f"{v.iv}:{state}:{t}", account=self.account, onset_ms=v.onset_ms,
                      sealed_ms=t, channel=Channel.VOICE, endpoint=v.endpoint,
                      refs=E.Refs(intervention_id=v.iv))

    def open_ids(self) -> set[str]:
        """The interventions this ear is still hearing (open or tentative)."""
        return {v.iv for v in self._voices.values() if v.state in OPEN_STATES and v.iv}

    def open_intervention(self, endpoint: str | None = None) -> tuple[str, int] | None:
        """(intervention, onset) of an open voice intervention — on that endpoint, or on any."""
        for v in self._voices.values():
            if v.state in OPEN_STATES and (endpoint is None or v.endpoint == endpoint):
                return v.iv, v.onset_ms
        return None

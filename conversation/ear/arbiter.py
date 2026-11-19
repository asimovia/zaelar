"""The ear: ONE arbiter decides when the person finished an intervention (§6.1, D1). Pure: no clock, no I/O.

A voice intervention moves open → (tentative ↔ extended) → closed, or → incomplete / discarded. It CLOSES only when
three things hold at once: the provider's end of turn (`EotHint(end)`), full coverage (every provider turn assigned
to it has its final, I2) and the watermark past the voice's last fall — so the last words cannot still be on their
way. Or, past the cap after the fall, with full coverage. Never by two detectors agreeing with each other (A6): an
eager hint only makes it TENTATIVE, and a tentative intervention is not delivered to anyone.

Without coverage at the cap, or with a stream that stopped beating (the watermark not advancing while time passes,
adapter doc A6), the intervention is INCOMPLETE: not actionable, the run asks for the end. Before its seal, voice that
resumes REOPENS a closed intervention (revision + 1); after it, the new voice is a new intervention that `amends` the
sealed one (I3). If a reopen loses the race to a seal (`Sealed` arrives for the earlier revision), the words heard
since the reopen move, all of them, to a new amending intervention — no word is in two (I2).

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


@dataclass
class _Voice:
    endpoint: str
    iv: str | None = None
    state: IvState | None = None
    rev: int = 0
    onset_ms: int = 0
    eot_end_ms: int | None = None
    eot_prob: float | None = None
    fall_ms: int | None = None
    watermark_ms: int | None = None
    expect: str | None = None
    amends: str | None = None
    last_sealed: str | None = None
    agent_spoke_since_seal: bool = False


class Ear:
    def __init__(self, account: str, config: Config, emitter: Emitter, ids: Ids) -> None:
        self.account, self.cfg, self.em, self.ids = account, config, emitter, ids
        self.spans = Spans()
        self._voices: dict[str, _Voice] = {}
        self._sealed: set[tuple[str, int]] = set()
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
            self._start_or_resume(v, sig.words[0][1], out)
        elif owner is not None and owner == v.iv and v.state is IvState.INCOMPLETE:
            self._reopen(v, t, out)           # the stream came back with the end of the same turn
        target = owner or v.iv
        if target is None:
            return
        grew = self.spans.add(sig.stream, sig.seq, sig.revision, sig.final, sig.words, target, v.rev)
        if grew and target == v.iv and v.state is IvState.TENTATIVE:
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
            if v.state in (IvState.CLOSED, IvState.INCOMPLETE) and (v.iv, v.rev) not in self._sealed:
                out.append(S.Onset(v.endpoint, sig.t_ms, v.iv))     # voice again: a reopen needs WORDS (a cough
                return                                               # is not a continuation)
            self._start_or_resume(v, sig.t_ms, out)

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
            self._v(sig.endpoint).agent_spoke_since_seal = True

    def _on_ContextHint(self, sig: S.ContextHint, out: list) -> None:
        self._v(sig.endpoint).expect = sig.expect

    def _on_TypedSubmit(self, sig: S.TypedSubmit, out: list) -> None:
        out.append(submit(self, sig, self._time(sig.t_ms)))

    def _on_Discard(self, sig: S.Discard, out: list) -> None:
        v = self._v(sig.endpoint)
        t = self._time(sig.t_ms)
        refs = {"endpoint": sig.endpoint, "channel": "voice"}
        if v.state in OPEN_STATES:
            refs.update(iv=v.iv, rev=v.rev)
            v.state = IvState.DISCARDED
            out.append(self._env_state(v, IvState.DISCARDED, t, text=sig.text, reason=sig.reason))
        self.em.emit("conv_ear", "discarded", owner="ear", cause={"kind": "guard", "ref": sig.reason}, refs=refs,
                     text=sig.text, reason=sig.reason)

    def _on_Sealed(self, sig: S.Sealed, out: list) -> None:
        self._sealed.add((sig.intervention_id, sig.revision))
        v = next((x for x in self._voices.values() if x.iv == sig.intervention_id), None)
        if v is None:
            return
        if v.state is IvState.CLOSED and v.rev == sig.revision:
            v.state, v.last_sealed, v.agent_spoke_since_seal = IvState.SEALED, v.iv, False
        elif v.state in OPEN_STATES and v.rev > sig.revision:
            # the reopen lost to the seal: what was heard since moves to a new intervention that amends it
            old, new = v.iv, self.ids.new("iv")
            self.spans.reassign(old, sig.revision + 1, new)
            v.last_sealed, v.agent_spoke_since_seal = old, False
            v.iv, v.rev, v.amends = new, 1, old
            out.append(self._env_state(v, IvState.OPEN, self._now))
            self.em.emit("conv_ear", "opened", owner="ear", cause={"kind": "seal", "ref": old},
                         refs={"iv": new, "rev": 1, "endpoint": v.endpoint, "channel": "voice"}, amends=old)

    # ── transitions ─────────────────────────────────────────────────────────────────────────────────────────────

    def _start_or_resume(self, v: _Voice, t: int, out: list) -> None:
        if v.state in OPEN_STATES:
            return
        if v.state in (IvState.CLOSED, IvState.INCOMPLETE) and (v.iv, v.rev) not in self._sealed:
            self._reopen(v, t, out)
            return
        v.amends = v.last_sealed if (v.state is IvState.SEALED and not v.agent_spoke_since_seal) else None
        v.iv, v.rev, v.state, v.onset_ms = self.ids.new("iv"), 1, IvState.OPEN, t
        v.eot_end_ms = v.eot_prob = v.fall_ms = None          # a fall of the previous intervention is not this one's
        out.append(S.Onset(v.endpoint, t, v.iv))
        out.append(self._env_state(v, IvState.OPEN, t))
        self.em.emit("conv_ear", "onset", owner="ear", cause={"kind": "voice"}, refs=self._refs(v), t_onset_ms=t)
        self.em.emit("conv_ear", "opened", owner="ear", cause={"kind": "voice"}, refs=self._refs(v),
                     amends=v.amends)

    def _reopen(self, v: _Voice, t: int, out: list) -> None:
        v.rev, v.state, v.eot_end_ms, v.fall_ms = v.rev + 1, IvState.OPEN, None, None
        out.append(S.Onset(v.endpoint, t, v.iv))
        out.append(self._env_state(v, IvState.OPEN, t, reopened=True))
        self.em.emit("conv_ear", "reopened", owner="ear", cause={"kind": "voice"}, refs=self._refs(v))

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
        if v.eot_end_ms is not None and covered and caught_up:
            self._close(v, t, "eot", out)
        elif v.fall_ms is not None and t - v.fall_ms >= cap:
            if not self.spans.words(v.iv):
                self._discard_empty(v, t, out)
            elif covered:
                self._close(v, t, "cap", out)
            else:
                self._incomplete(v, t, "no_final", out)
        elif v.watermark_ms is not None and t - v.watermark_ms >= self.cfg.stall_ms:
            self._incomplete(v, t, "stalled", out)

    def _close(self, v: _Voice, t: int, by: str, out: list) -> None:
        v.state = IvState.CLOSED
        words = self.spans.words(v.iv)
        body = E.UtteranceBody(v.iv, v.rev, " ".join(w[0] for w in words),
                               tuple(E.Span(*w) for w in words), amends=v.amends)
        out.append(E.make(EnvelopeKind.USER_UTTERANCE, body, producer=f"ear:{v.endpoint}",
                          producer_id=f"{v.iv}:{v.rev}:closed", account=self.account, onset_ms=v.onset_ms,
                          sealed_ms=t, channel=Channel.VOICE, endpoint=v.endpoint,
                          refs=E.Refs(intervention_id=v.iv, revision=v.rev)))
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
        v.state = IvState.INCOMPLETE
        text = " ".join(w[0] for w in self.spans.words(v.iv))
        out.append(self._env_state(v, IvState.INCOMPLETE, t, text=text, reason=reason))
        self.em.emit("conv_ear", "incomplete", owner="ear", cause={"kind": "cap" if reason == "no_final"
                                                                   else "stall"},
                     refs=self._refs(v), text=text, reason=reason, watermark_ms=v.watermark_ms)

    # ── out ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def _refs(self, v: _Voice) -> dict:
        return {"iv": v.iv, "rev": v.rev, "endpoint": v.endpoint, "channel": "voice"}

    def _env_state(self, v: _Voice, state: IvState, t: int, *, text: str | None = None, reason: str | None = None,
                   reopened: bool = False) -> E.Envelope:
        label = E.REOPENED if reopened else str(state)
        body = E.InterventionStateBody(v.iv, state, v.rev, text, E.REOPENED if reopened else reason)
        return E.make(EnvelopeKind.INTERVENTION_STATE, body, producer=f"ear:{v.endpoint}",
                      producer_id=f"{v.iv}:{v.rev}:{label}:{t}", account=self.account, onset_ms=v.onset_ms,
                      sealed_ms=t, channel=Channel.VOICE, endpoint=v.endpoint,
                      refs=E.Refs(intervention_id=v.iv, revision=v.rev))

    def open_ids(self) -> set[str]:
        """The interventions this ear is still hearing (open or tentative)."""
        return {v.iv for v in self._voices.values() if v.state in OPEN_STATES and v.iv}

    def open_intervention(self, endpoint: str | None = None) -> tuple[str, int, int] | None:
        """(intervention, revision, onset) of an open voice intervention — on that endpoint, or on any."""
        for v in self._voices.values():
            if v.state in OPEN_STATES and (endpoint is None or v.endpoint == endpoint):
                return v.iv, v.rev, v.onset_ms
        return None

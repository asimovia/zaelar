"""An ear and an inbox wired together over one store, as the manager will wire them: every envelope the ear (or a
test) produces is accepted at the time it carries."""
from __future__ import annotations

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import Ear
from conversation.ear import signals as S
from conversation.inbox import Inbox
from conversation.telemetry import Emitter
from conversation.types import ControlOp, EnvelopeKind

ACCT = "acct-test"


class Pipe:
    def __init__(self, store, clock, telemetry, config: Config | None = None) -> None:
        from conversation.types import Ids
        self.cfg = config or Config()
        self.store, self.clock, self.tel = store, clock, telemetry
        self.lease = store.acquire(ACCT, "test")
        em = Emitter(telemetry, clock, ACCT)
        ids = Ids()
        self.ear = Ear(ACCT, self.cfg, em, ids)
        self.inbox = Inbox(store, lambda: self.lease, ACCT, self.cfg, em, ids)
        self.admissions: list = []

    def at(self, t: int) -> "Pipe":
        self.clock.mono = t
        return self

    def now(self) -> int:
        return self.clock.mono

    def signal(self, *sigs) -> list:
        out = []
        for sig in sigs:
            for one in (sig if isinstance(sig, list) else [sig]):
                t = getattr(one, "t_ms", None) or getattr(one, "processed_through_ms", None) or (
                    one.window[1] if isinstance(one, S.WordSpan) else None)
                if t is not None:
                    self.clock.mono = max(self.clock.mono, t)
                for item in self.ear.feed(one):
                    if isinstance(item, S.Onset):              # as the manager does: an open voice holds texts
                        self.inbox.voice_open(item.intervention_id, item.t_ms, item.endpoint)
                    elif isinstance(item, S.VoiceDiscarded):
                        self.inbox.voice_done(item.intervention_id, self.now())
                    elif isinstance(item, E.Envelope):
                        adm = self.inbox.accept(item, self.now())
                        self.admissions.append(adm)
                        out.append(adm)
        return out

    def give(self, env: E.Envelope) -> object:
        adm = self.inbox.accept(env, self.now())
        self.admissions.append(adm)
        return adm

    def batch(self):
        self.inbox.sweep(self.now())
        return self.inbox.next_batch(self.now())


def control(op: ControlOp, t: int, n: str, endpoint="d2", gesture=False, handle=None, channel=None, task=None):
    from conversation.types import Channel
    return E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(op, handle_id=handle, task_id=task, gesture=gesture),
                  producer=f"button:{endpoint}", producer_id=n, account=ACCT, onset_ms=t, sealed_ms=t,
                  channel=channel or Channel.BUTTON, endpoint=endpoint)


def kinds(batch) -> list[str]:
    return [str(e.kind) for e in batch.envelopes]

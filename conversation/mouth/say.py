"""The mouth: say, and know what was HEARD — and «unknown» when nobody acknowledged.

`say` records the order (a `says` row: the line, its trace, heard: unknown) and hands it to the `Mouth` port, which
has two verbs, say and stop. The acks come back as signals: `SayStarted`, and `SayEnded` (played · cut · cleared ·
unknown) with how much was heard and where that comes from: `agent_estimate` (the voice process's count of what it
spoke), `shown` (a text line painted on a screen the person is looking at), or `unknown`. Nothing is ever assumed
heard: a line with no count stays «heard: unknown» in the conversation the model reads. A cut keeps what was heard,
trimmed back to the last sentence boundary inside it; cutting our voice never touches the record of an action.

Every event of a line carries its trace: the root of the request it answers, or the key of the line owed it says. A
stop carries the trace of the line it cuts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from conversation import guard
from conversation.config import Config
from conversation.ports import Clock, Lease, Mouth, SayOrder, Store
from conversation.telemetry import Emitter
from conversation.types import Ids

SAYS = "says"
SENTENCE_ENDS = ".!?…"
LIVE = ("ordered", "playing")


@dataclass(frozen=True)
class SayStarted:
    say_id: str
    t_ms: int


@dataclass(frozen=True)
class SayEnded:
    say_id: str
    outcome: str               # played · cut · cleared · unknown
    heard_chars: int | None
    t_ms: int
    endpoint: str | None = None
    source: str = "agent_estimate"   # where `heard_chars` comes from: agent_estimate · shown · unknown


def cut_to_sentence(text: str, heard_chars: int) -> str:
    """What was heard, back to the last sentence end inside it (or every word heard, if no sentence ended)."""
    heard = text[:max(0, heard_chars)]
    ends = [i for i, ch in enumerate(heard) if ch in SENTENCE_ENDS]
    if ends:
        return heard[:ends[-1] + 1]
    return heard[:heard.rfind(" ")] if " " in heard and heard_chars < len(text) else heard


class Speaker:
    def __init__(self, store: Store, lease: Callable[[], Lease], mouth: Mouth, emitter: Emitter, clock: Clock,
                 ids: Ids, on_owed: Callable[[str, bool], None] | None = None,
                 on_ended: Callable[[str], None] | None = None, config: Config | None = None) -> None:
        self.store, self.lease, self.mouth, self.em, self.clock, self.ids = store, lease, mouth, emitter, clock, ids
        self.on_owed = on_owed or (lambda key, sounded: None)   # a line owed ended: did it sound?
        self.on_ended = on_ended or (lambda say_id: None)       # a line ended, whatever the outcome
        self.cfg = config or Config()

    def overdue(self, now: int) -> list[str]:
        """Lines with no `SayEnded` past their bound: acks get lost, and nobody waits on one forever."""
        with self.store.tx(self.lease()) as tx:            # the lines in course, never the history
            live = tx.scan(SAYS, states=LIVE)
        return [k for k, row in live if now - row["t_ms"] >= self.cfg.say_end_ms + 80 * len(row["text"])]

    def _refs(self, row: dict) -> dict:
        return {"say": row["say_id"], "run": row["run"], "req": row["req"], "endpoint": row.get("endpoint")}

    async def say(self, *, run_id: str, request_id: str, text: str, channels: frozenset[str], endpoint: str | None,
                  trace: str, lang: str = "", iv: str | None = None, notice_key: str | None = None) -> str:
        say_id = self.ids.new("s")
        row = {"say_id": say_id, "run": run_id, "req": request_id, "text": text, "channels": sorted(channels),
               "endpoint": endpoint, "state": "ordered", "heard_chars": None, "heard_source": "unknown",
               "outcome": None, "t_ms": self.clock.now_ms(), "notice_key": notice_key, "trace": trace, "iv": iv}
        with self.store.tx(self.lease()) as tx:
            tx.put(SAYS, say_id, row)
        self.em.emit("conv_mouth", "say", owner="mouth", cause={"kind": "run", "ref": run_id}, refs=self._refs(row),
                     trace=trace, channels=sorted(channels), chars=len(text), notice_key=notice_key)
        try:
            await guard.call(self.em, self.cfg, "mouth", self.mouth.say(SayOrder(say_id, run_id, request_id, text,
                                                                                 frozenset(channels), endpoint, lang,
                                                                                 notice_key)),
                             self.cfg.mouth_ms, {"say": say_id, "run": run_id})
        except guard.PortTimeout:              # the order went unanswered: the line ended «unknown», nobody waits on it
            self.ack(SayEnded(say_id, "unknown", None, self.clock.now_ms(), endpoint, "unknown"))
        return say_id

    def ack(self, sig: SayStarted | SayEnded) -> None:
        with self.store.tx(self.lease()) as tx:
            row = tx.get(SAYS, sig.say_id)
            if row is None or row["state"] == "ended":
                return
            label, extra = self._apply(row, sig)
            tx.put(SAYS, sig.say_id, row)
        self.em.emit("conv_mouth", label, owner="mouth", cause={"kind": "ack"}, refs=self._refs(row),
                     trace=row["trace"], **extra)
        if row.get("notice_key") and isinstance(sig, SayEnded):
            # it sounded if it played, or a cut came after it began; an unknown end or a cut before any sound did not
            self.on_owed(row["notice_key"], sig.outcome == "played" or bool(row["heard_chars"]))
        if isinstance(sig, SayEnded):
            self.on_ended(sig.say_id)

    @staticmethod
    def _apply(row: dict, sig) -> tuple[str, dict]:
        if isinstance(sig, SayStarted):
            row["state"] = "playing"
            return "started", {}
        row["state"], row["outcome"] = "ended", sig.outcome
        known = sig.heard_chars is not None and "unknown" not in (sig.outcome, sig.source)
        if known:
            cut = sig.outcome in ("cut", "cleared")
            row["heard_chars"] = len(cut_to_sentence(row["text"], sig.heard_chars) if cut
                                     else row["text"][:sig.heard_chars])
            row["heard_source"] = sig.source
        label = "cut" if sig.outcome in ("cut", "cleared") else "ended"
        return label, {"outcome": sig.outcome, "heard_chars": row["heard_chars"], "source": row["heard_source"]}

    def voice_unavailable(self, run_id: str, endpoint: str | None, trace: str) -> None:
        """The batch had voice and this device cannot speak now: the reply goes as text, and that is said."""
        self.em.emit("conv_mouth", "voice_unavailable", owner="mouth", cause={"kind": "device"},
                     refs={"run": run_id, "endpoint": endpoint}, trace=trace)

    def stop(self, endpoint: str | None, reason: str, asked_ms: int, trace: str | None = None) -> None:
        """The control lane: immediate and local, never through the inbox. Its event carries the trace of the line it
        cuts (the newest in course), else the one the caller names (the run, the control)."""
        self.mouth.stop(endpoint, reason=reason)
        with self.store.tx(self.lease()) as tx:
            live = [r for _k, r in tx.scan(SAYS, states=LIVE)]
        line = max(live, key=lambda r: r["t_ms"], default=None)
        self.em.emit("conv_mouth", "cut", owner="mouth", cause={"kind": "control", "ref": reason},
                     refs={"endpoint": endpoint, "say": line["say_id"] if line else None,
                           "run": line["run"] if line else None},
                     trace=line["trace"] if line else trace, stop_to_silence_ms=self.clock.mono_ms() - asked_ms)

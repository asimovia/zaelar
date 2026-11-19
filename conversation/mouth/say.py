"""The mouth: say, and know what was HEARD — per device, and «unknown» when nobody acknowledged (B4, A7 of the
adapter doc).

`say` records the order (a `says` row and the agent's line in the conversation, heard: unknown) and hands it to the
`Mouth` port. The acks come back as signals: `SayStarted`, `PlayoutAck` (a device played up to N characters),
`Painted` (a device showed the text), `SayEnded` (played · cut · cleared · unknown). Nothing is ever assumed heard:
a line with no ack stays «heard: unknown» in the conversation the model reads. A cut keeps what was heard, trimmed back
to the last sentence boundary inside it; cutting our voice never touches the record of an action (the ledger). A
question that needs a yes counts as PRESENTED only once it was played, or painted on a device's text channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from conversation import guard
from conversation.config import Config
from conversation.ports import Clock, Lease, Mouth, SayOrder, Store
from conversation.telemetry import Emitter
from conversation.types import Ids

SAYS, TURNS = "says", "turns"
SENTENCE_ENDS = ".!?…"


@dataclass(frozen=True)
class SayStarted:
    say_id: str
    t_ms: int


@dataclass(frozen=True)
class PlayoutAck:
    say_id: str
    endpoint: str
    heard_chars: int | None
    t_ms: int


@dataclass(frozen=True)
class Painted:
    say_id: str
    endpoint: str
    t_ms: int


@dataclass(frozen=True)
class SayEnded:
    say_id: str
    outcome: str               # played · cut · cleared · unknown
    heard_chars: int | None
    t_ms: int
    endpoint: str | None = None


def cut_to_sentence(text: str, heard_chars: int) -> str:
    """What was heard, back to the last sentence end inside it (or every word heard, if no sentence ended)."""
    heard = text[:max(0, heard_chars)]
    ends = [i for i, ch in enumerate(heard) if ch in SENTENCE_ENDS]
    if ends:
        return heard[:ends[-1] + 1]
    return heard[:heard.rfind(" ")] if " " in heard and heard_chars < len(text) else heard


class Speaker:
    def __init__(self, store: Store, lease: Callable[[], Lease], mouth: Mouth, emitter: Emitter, clock: Clock,
                 ids: Ids, on_presented: Callable[[str, str | None], None] | None = None,
                 config: Config | None = None) -> None:
        self.store, self.lease, self.mouth, self.em, self.clock, self.ids = store, lease, mouth, emitter, clock, ids
        self.on_presented = on_presented or (lambda handle, endpoint: None)
        self.cfg = config or Config()

    def overdue(self, now: int) -> list[str]:
        """Lines with no `SayEnded` past their bound: acks get lost, and nobody waits on one forever (B2)."""
        snap = self.store.snapshot(self.lease().account)
        return [k for k, row in snap.scan(SAYS) if row["state"] != "ended"
                and now - row["t_ms"] >= self.cfg.say_end_ms + 80 * len(row["text"])]

    def _refs(self, row: dict) -> dict:
        return {"say": row["say_id"], "run": row["run"], "req": row["req"], "endpoint": row.get("endpoint")}

    async def say(self, *, run_id: str, request_id: str, text: str, channels: frozenset[str], endpoint: str | None,
                  lang: str = "", presents: str | None = None, iv: str | None = None) -> str:
        say_id = self.ids.new("s")
        row = {"say_id": say_id, "run": run_id, "req": request_id, "text": text, "channels": sorted(channels),
               "endpoint": endpoint, "presents": presents, "state": "ordered", "heard": {}, "painted": [],
               "outcome": None, "t_ms": self.clock.now_ms()}
        with self.store.tx(self.lease()) as tx:
            tx.put(SAYS, say_id, row)
            seq = tx.next_seq(TURNS)
            tx.put(TURNS, f"{seq:08d}", {"role": "agent", "channel": "+".join(sorted(channels)), "text": text,
                                        "heard_chars": None, "ref": say_id, "iv": iv})
        self.em.emit("conv_mouth", "say", owner="mouth", cause={"kind": "run", "ref": run_id}, refs=self._refs(row),
                     channels=sorted(channels), chars=len(text), presents=presents)
        await guard.call(self.em, self.cfg, "mouth", self.mouth.say(SayOrder(say_id, run_id, request_id, text,
                                                                             frozenset(channels), endpoint, lang,
                                                                             presents)),
                         self.cfg.mouth_ms, {"say": say_id, "run": run_id})
        return say_id

    def ack(self, sig: SayStarted | PlayoutAck | Painted | SayEnded) -> None:
        with self.store.tx(self.lease()) as tx:
            row = tx.get(SAYS, sig.say_id)
            if row is None:
                return
            label, extra = self._apply(tx, row, sig)
            tx.put(SAYS, sig.say_id, row)
        self.em.emit("conv_mouth", label, owner="mouth", cause={"kind": "ack"}, refs=self._refs(row), **extra)
        if extra.get("presented"):
            self.on_presented(row["presents"], extra.get("presented_on"))

    def _apply(self, tx, row: dict, sig) -> tuple[str, dict]:
        if isinstance(sig, SayStarted):
            row["state"] = "playing"
            return "started", {}
        if isinstance(sig, Painted):
            row["painted"] = sorted(set(row["painted"]) | {sig.endpoint})
            first = bool(row["presents"]) and "text" in row["channels"] and not row.get("presented")
            row["presented"] = row.get("presented") or first
            return "ack", {"heard_chars": None, "painted": True, "presented": first, "presented_on": sig.endpoint}
        if isinstance(sig, PlayoutAck):
            row["heard"][sig.endpoint] = sig.heard_chars
            return "ack", {"heard_chars": sig.heard_chars}
        row["state"], row["outcome"] = "ended", sig.outcome
        heard = sig.heard_chars
        if heard is None:                       # the device's own ack, if it sent one; else still unknown
            heard = row["heard"].get(sig.endpoint or row["endpoint"] or "")
        self._trim_turn(tx, row, heard, cut=sig.outcome in ("cut", "cleared"))
        first = bool(row["presents"]) and sig.outcome == "played" and not row.get("presented")
        row["presented"] = row.get("presented") or first
        label = "cut" if sig.outcome in ("cut", "cleared") else "ended"
        return label, {"outcome": sig.outcome, "heard_chars": heard, "presented": first,
                       "presented_on": sig.endpoint or row["endpoint"]}

    def _trim_turn(self, tx, row: dict, heard: int | None, *, cut: bool) -> None:
        for key, turn in tx.scan(TURNS):
            if turn.get("ref") != row["say_id"]:
                continue
            if heard is None:
                turn["heard_chars"] = None
            else:
                kept = cut_to_sentence(row["text"], heard) if cut else row["text"][:heard]
                turn["heard_chars"] = len(kept)
            tx.put(TURNS, key, turn)

    def voice_unavailable(self, run_id: str, endpoint: str | None) -> None:
        """The batch had voice and this device cannot speak now: the reply goes as text, and that is said."""
        self.em.emit("conv_mouth", "voice_unavailable", owner="mouth", cause={"kind": "device"},
                     refs={"run": run_id, "endpoint": endpoint})

    # the control lane: immediate and local, never through the inbox
    def duck(self, endpoint: str) -> None:
        self.mouth.duck(endpoint)
        self.em.emit("conv_mouth", "ducked", owner="mouth", cause={"kind": "onset"}, refs={"endpoint": endpoint})

    def unduck(self, endpoint: str) -> None:
        self.mouth.unduck(endpoint)
        self.em.emit("conv_mouth", "unducked", owner="mouth", cause={"kind": "control"}, refs={"endpoint": endpoint})

    def stop(self, endpoint: str | None, reason: str, asked_ms: int) -> None:
        self.mouth.stop(endpoint, reason=reason)
        self.em.emit("conv_mouth", "cut", owner="mouth", cause={"kind": "control", "ref": reason},
                     refs={"endpoint": endpoint}, stop_to_silence_ms=self.clock.mono_ms() - asked_ms)

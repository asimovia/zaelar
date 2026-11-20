"""Replay a recorded session — ear signals in tokens, with their times — through the whole manager (P2).

    python -m conversation.replay <signals.jsonl> [--events out.jsonl] [--think-ms 800]

The signals are the converter's (`tests/conversation/tools/export_envelopes.py`): `WordSpan`, `VadEdge`, `EotHint`,
`Watermark`, `TypedSubmit`, `Control` (a stop from the safety guard), `PlaybackState` and `AgentLine` (what the agent of
the recording did: not replayed — this manager answers on its own). Between the recorded signals the provider's
watermark is filled in every 240 ms, as Flux sends it while the microphone streams (adapter doc A2). The model is
scripted (it answers by id, never by text) and THINKS `think_ms` of simulated time before answering — the recorded
signals of that span arrive while it runs, so a continuation during the model's turn reaches a checkpoint exactly as
it would live. `--events` writes the manager's events in the observer's shape (`i, t_ms, kind, label, extra, trace,
piece`), for the viewers; the piece of an event is `c_<owner>`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace

from conversation import envelopes as E
from conversation.config import Config
from conversation.ear import signals as S
from conversation.manager import Conversation
from conversation.ports import Done, ToolCall
from conversation.testing.fakes import AckingMouth, FakeClock, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.generate import AuditedStore
from conversation.testing.scripted_model import ScriptedModel, reply
from conversation.types import Channel, ControlOp, EnvelopeKind

ACCOUNT = "replay"
BEAT_MS = 240
KEEP_TIME_MS = 250          # the live loop's own timer (`Conversation.keep_time`)


def load(lines) -> list[dict]:
    return [json.loads(line) for line in lines if line.strip()]


def _time(s: dict) -> int:
    if "t_ms" in s:
        return s["t_ms"]
    if "processed_through_ms" in s:
        return s["processed_through_ms"]
    return s["window"][1]


def _signal(s: dict):
    kind = s["sig"]
    if kind == "WordSpan":
        return S.WordSpan(s["stream"], s["seq"], s["revision"], s["final"],
                          tuple((w, a, b, c) for w, a, b, c in s["words"]), tuple(s["window"]))
    if kind == "VadEdge":
        return S.VadEdge(s["endpoint"], s["edge"], s["t_ms"], s.get("echo_safe", True))
    if kind == "EotHint":
        return S.EotHint(s["stream"], s["source"], s["kind"], s["prob"], s["t_ms"], s.get("terminal"))
    if kind == "Watermark":
        return S.Watermark(s["stream"], s["processed_through_ms"])
    if kind == "TypedSubmit":
        return S.TypedSubmit(s["endpoint"], s["client_id"], s["text"], s["t_ms"])
    return None                                  # Control is an envelope; the recorded agent is not replayed


def with_beats(signals: list[dict]) -> list[dict]:
    """The provider's watermark every 240 ms on every stream, from its first signal to the last of the session."""
    streams = sorted({s.get("stream") or s.get("endpoint") for s in signals if s["sig"] in ("WordSpan", "VadEdge")})
    if not signals:
        return []
    t0, t1 = min(_time(s) for s in signals), max(_time(s) for s in signals)
    beats = [{"sig": "Watermark", "stream": st, "processed_through_ms": t}
             for st in streams for t in range(t0, t1 + BEAT_MS, BEAT_MS)]
    return sorted(signals + beats, key=_time)


@dataclass
class Replay:
    signals: list[dict]
    think_ms: int = 800
    config: Config = field(default_factory=Config)

    def __post_init__(self) -> None:
        self.queue = with_beats(self.signals)
        self.i, self._pumped = 0, -1 << 62
        start = _time(self.queue[0]) if self.queue else 0
        self.clock = FakeClock(t0_ms=start)
        self.tel, self.tools, self.mouth = ListTelemetry(), RecordingTools(), AckingMouth()
        self.model = ScriptedModel(default=self._answer)
        self.store = AuditedStore()
        self.conv = Conversation(account=ACCOUNT, owner="replay", model=self.model, tools=self.tools,
                                 store=self.store, memory=NoMemory(), clock=self.clock, mouth=self.mouth,
                                 telemetry=self.tel, config=self.config, prefix="REPLAY")
        self.mouth.ack = self.conv.ack
        # our own voice reaches the ear as the device's playback, as it would live
        self.mouth.playback = lambda ep: self.conv.hear(S.PlaybackState(ep, True, self.clock.now_ms()))
        for ep in sorted({x.get("endpoint") or x.get("stream") for x in self.signals} - {None}):
            self.conv.device(ep, voice_live=True, speaker_open=True)     # the recorded devices had a live voice
        self.n, self.asked, self.issued = 0, 0, 0
        self.loop = asyncio.new_event_loop()

    def _answer(self, ids: list[str]) -> list:
        """Think, then answer; every third request also reads, acts here and asks for a send first, so the replay
        exercises the gateway (the read passes, the local act is reserved and sent once, the send is held) and I8 has
        something to check."""
        self.asked += 1
        what = ids[0] if ids else "w0"
        act = ([ToolCall(f"r{self.asked}", "search", {"q": what}),
                ToolCall(f"a{self.asked}", "agenda_add", {"what": what}),
                ToolCall(f"s{self.asked}", "send_message", {"to": "c1", "text": what})]
               if self.asked % 3 == 0 else [])
        self.issued += len(act)
        return [lambda: self.until(self.clock.now_ms() + self.think_ms), *act, reply("ok " + "+".join(ids)), Done()]

    def _feed(self, s: dict) -> None:
        t = _time(s)
        self.clock.mono = max(self.clock.mono, t - self.clock.wall0)
        if s["sig"] == "Control":
            self.n += 1
            self.conv.give(E.make(EnvelopeKind.USER_CONTROL, E.ControlBody(ControlOp(s["op"])),
                                  producer=f"guard:{s['endpoint']}", producer_id=f"g{self.n}", account=ACCOUNT,
                                  onset_ms=t, sealed_ms=t, channel=Channel.VOICE, endpoint=s["endpoint"]))
            return
        sig = _signal(s)
        if sig is not None:
            self.conv.hear(sig)

    def until(self, t_ms: int) -> None:
        """Feed every recorded signal up to `t_ms` (called by the model while it thinks: no nested runs)."""
        while self.i < len(self.queue) and _time(self.queue[self.i]) <= t_ms:
            self._feed(self.queue[self.i])
            self.i += 1
            now = self.clock.now_ms()
            if self.conv.pumpable and (self.conv.dirty or now - self._pumped >= KEEP_TIME_MS):
                self._pumped = now                # as the live loop: on what was accepted, and on its keep_time
                self.loop.run_until_complete(self.conv.pump())
        self.clock.mono = max(self.clock.mono, t_ms - self.clock.wall0)

    def run(self) -> "Replay":
        while self.i < len(self.queue):
            self.until(_time(self.queue[self.i]))
        cfg = self.config                          # the end: time runs out on the live timer, whatever is ready runs
        span = max(cfg.liveness_ms, cfg.cross_channel_hold_ms, cfg.intervention_max_ms, cfg.close_cap_ms) + 1
        for _ in range(3 * (span // 1000 + 1)):
            self.clock.advance(1000)
            self.conv.hear(S.Tick(self.clock.now_ms()))
            self.loop.run_until_complete(self.conv.pump())
        self.loop.close()
        return self

    def as_case(self) -> SimpleNamespace:
        """The shape `conversation.testing.generate.check` reads, to judge I1–I9 on a replay."""
        return SimpleNamespace(crashes=[], store=self.store, conv=self.conv, old=None, tel=self.tel, cfg=self.config,
                               mouth=self.mouth,
                               clock=self.clock, tools=self.tools, model=self.model, issued_calls=self.issued, race_seals=[],
                               account=ACCOUNT)

    def observer_events(self) -> list[dict]:
        return [{"i": i, "t_ms": p["t_ms"], "kind": k, "label": lab, "trace": p.get("trace", ""),
                 "piece": f"c_{p['owner']}" if not p["owner"].startswith("worker:") else "c_manager", "extra": p}
                for i, (k, lab, p) in enumerate(self.tel.events, start=1)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("signals")
    ap.add_argument("--events", help="write the manager's events here, in the observer's shape")
    ap.add_argument("--think-ms", type=int, default=800)
    args = ap.parse_args(argv)
    with open(args.signals, encoding="utf-8") as fh:
        rep = Replay(load(fh), think_ms=args.think_ms).run()
    if args.events:
        with open(args.events, "w", encoding="utf-8") as fh:
            for ev in rep.observer_events():
                fh.write(json.dumps(ev) + "\n")
    runs = rep.tel.labels("conv_run").count("conv_run/started")
    print(json.dumps({"signals": len(rep.signals), "runs": runs, "says": len(rep.mouth.orders),
                      "closes": len([1 for k, _l, _p in rep.tel.events if k == "conv_close"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

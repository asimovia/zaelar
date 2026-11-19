"""P8 skeleton (node 13.23): the process dies before or after each transition and a new one takes the same store.

Accept, close, seal, reserve, submit, the provider's answer, the recorded receipt, a playout ack — at each one, before
and after, the process is killed (`conversation.testing.faults`), a new manager acquires the account on the SAME
sqlite file, recovers what the dead one left (a dequeued batch back to the queue, an effect left `submitting` →
`submission_unknown`), and the conversation goes on. Then: no effect reached the provider twice, an unknown
submission was never resent, every request ended, and the inbox is drained clean. No run reserves an effect in F1
(nothing but a read passes), so the reservation's points are driven through its own door, as F2 will.
"""
from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from conversation import build
from conversation.config import Config
from conversation.ear import signals as S
from conversation.inbox.accounting import audit
from conversation.gateway import dispatch
from conversation.gateway.authority import RunCtx
from conversation import envelopes as E
from conversation.ports import Done, ToolCall
from conversation.store import SqliteStore
from conversation.testing.faults import Crash, Point, inject
from conversation.testing.fakes import AckingMouth, FakeClock, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.scripted_model import ScriptedModel, reply

ACCT = "acct-test"


def _script():
    return ScriptedModel(default=lambda ids: (
        [ToolCall("a", "search", {"q": "w1"}), Done()]
        if ids and ids[0].startswith("iv") else [reply("w-told"), Done()]))


class Process:
    """One process of the engine: a manager over the store file, the same provider (tools) across restarts."""

    def __init__(self, path, clock, tools) -> None:
        self.store = SqliteStore(path)
        self.tel, self.mouth, self.model = ListTelemetry(), AckingMouth(), _script()
        self.conv = build(account=ACCT, owner="p", model=self.model, tools=tools, store=self.store,
                          memory=NoMemory(), clock=clock, mouth=self.mouth, telemetry=self.tel,
                          config=Config(liveness_ms=30_000), prefix="P8")
        self.mouth.ack = self.conv.ack
        self.conv.device("d1", voice_live=True, speaker_open=True)

    def pump(self) -> None:
        asyncio.run(self.conv.pump())


def _speak(p: Process, clock) -> None:
    t = clock.mono + 10
    ws = (("w1", t, t + 150, 1.0), ("w2", t + 160, t + 300, 1.0))
    for sig in (S.VadEdge("d1", "rise", t), S.WordSpan("d1", 1, 1, True, ws, (t, t + 300)),
                S.VadEdge("d1", "fall", t + 310), S.Watermark("d1", t + 400), S.EotHint("d1", "flux", "end", .9,
                                                                                             t + 450)):
        clock.mono = max(clock.mono, getattr(sig, "t_ms", None) or getattr(sig, "processed_through_ms", 0))
        p.conv.hear(sig)
    p.pump()


def _act(p: Process) -> None:
    """F2's path, driven by hand: reserve an effect on the person's first entry and submit it."""
    rows = [r for _k, r in p.store.snapshot(ACCT).scan("inbox") if r["kind"] == "user.utterance"]
    if not rows:
        return
    env = E.from_json(rows[0]["env"])
    got = p.conv.gw.reserve(RunCtx("run-act", f"r_{env.refs.intervention_id}", {env.id: env}, "d1"),
                            ToolCall("a", "agenda_add", {"what": "w1"}))
    if hasattr(got, "effect_id"):
        asyncio.run(dispatch.submit(p.conv.gw, p.conv.tools, got.effect_id, 10 ** 12))


CASES = [(pt, when) for pt in Point for when in ("before", "after")
         if not (pt in (Point.SUBMIT,) and when == "after") and not (pt in (Point.PROVIDER, Point.RECEIPT)
                                                                     and when == "before")]


@pytest.mark.parametrize("point,when", CASES, ids=[f"{p.value}-{w}" for p, w in CASES])
def test_a_crash_at_any_transition_recovers(tmp_path, point, when):
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    crashed = False
    with inject(point, when, tools=tools) as fired:
        try:
            _speak(first, clock)
            _act(first)
        except Crash:
            crashed = True
    assert crashed == bool(fired["n"]), "the armed point was never reached"
    second = Process(path, clock, tools)                       # the same file, a new lease: the dead one is fenced
    second.pump()
    _act(second)
    for _ in range(3):                                         # time runs out: every budget expires, what is ready runs
        clock.advance(31_000)
        second.conv.sweep()
        second.pump()
    calls = Counter(eid for _name, _args, eid in tools.calls if eid)
    assert all(n == 1 for n in calls.values()), f"an effect reached the provider twice: {calls}"
    snap = second.store.snapshot(ACCT)
    items = [r for _k, r in snap.scan("items")]
    assert not [r["id"] for r in items if r["kind"] == "request" and r["state"] == "open"], "a request never ended"
    assert audit(snap, clock.now_ms(), second.conv.cfg, drained=True) == []
    unknown = [r["id"] for r in items if r["kind"] == "effect" and r["state"] == "submission_unknown"]
    assert all(calls.get(e, 0) <= 1 for e in unknown)
    second.store.close()
    first.store.close()


def test_a_crash_after_the_provider_answered_leaves_an_unknown_submission_that_is_never_resent(tmp_path):
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    _speak(first, clock)
    with inject(Point.PROVIDER, "after", tools=tools):
        with pytest.raises(Crash):
            _act(first)
    second = Process(path, clock, tools)
    second.pump()
    _act(second)
    effect = [r for _k, r in second.store.snapshot(ACCT).scan("items") if r["kind"] == "effect"][0]
    assert effect["state"] == "submission_unknown"
    assert [c[0] for c in tools.calls if c[2]] == ["agenda_add"]   # the rerun found the same row and did not resend
    second.store.close()
    first.store.close()

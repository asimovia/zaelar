"""P8 (node 13.23): the process dies before or after each transition and a new one takes the same store.

The transitions of a SENTENCE — its voice opened, its envelope accepted, its intervention closed, sealed at the
publication, a playout ack — each armed while that sentence goes through it: every case asserts the point fired. A
new manager acquires the account on the SAME sqlite file and recovers what the dead one left: a dequeued batch back to
the queue, and a voice it was hearing ended incomplete (reason `restart`, R3-B1) so the run asks for it again. Then,
case by case: the sentence ended answered — whole, or incomplete and said — every request ended, no voice is left
open, and the inbox drains clean.

The reservation's transitions (reserve, submit, the provider's answer, the recorded receipt) are driven through its
own door, since no run reserves in F1: no effect reaches the provider twice, and an unknown submission is never resent.
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
from tests.conversation.conftest import zaelar_store
from conversation.testing.faults import SENTENCE, Crash, Point, inject
from conversation.testing.fakes import AckingMouth, FakeClock, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.scripted_model import ScriptedModel, reply

ACCT = "acct-test"


def _script():
    return ScriptedModel(default=lambda ids: [reply("w-told " + "+".join(ids)), Done()])


class Process:
    """One process of the engine: a manager over the store file, the same provider (tools) across restarts."""

    def __init__(self, path, clock, tools) -> None:
        self.store = zaelar_store(path)
        self.tel, self.mouth, self.model = ListTelemetry(), AckingMouth(), _script()
        from conversation.testing.fakes import FakeOwed
        self.owed = FakeOwed()
        self.conv = build(account=ACCT, owner="p", model=self.model, tools=tools, store=self.store,
                          memory=NoMemory(), clock=clock, mouth=self.mouth, telemetry=self.tel,
                          config=Config(liveness_ms=30_000), prefix="P8", owed=self.owed)
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
    clock.advance(p.conv.cfg.terminal_grace_ms + 100)          # the reply waits its grace, then goes out
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


def _drain(second: Process, clock) -> None:
    second.pump()
    for _ in range(93):                                        # time runs out on the live timer: every budget expires,
        clock.advance(1000)                                    # what is ready runs
        second.conv.sweep()
        second.pump()


#: dying BEFORE the open voice is written is dying before the person spoke, as far as this store knows: the voice
#: lane of the host re-delivers what it had not handed over — not a case of this package
SENTENCE_CASES = [(pt, when) for pt in SENTENCE for when in ("before", "after") if (pt, when) != (Point.OPEN, "before")]


@pytest.mark.parametrize("point,when", SENTENCE_CASES, ids=[f"{p.value}-{w}" for p, w in SENTENCE_CASES])
def test_a_crash_while_a_sentence_goes_through_recovers_it(tmp_path, point, when):
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    with inject(point, when, tools=tools) as fired:
        with pytest.raises(Crash):
            _speak(first, clock)
    assert fired["n"] == 1, "the armed point was never reached by the sentence"
    second = Process(path, clock, tools)                       # the same file, a new lease: the dead one is fenced
    _drain(second, clock)
    snap = second.store.snapshot(ACCT)
    requests = {r["id"]: r["state"] for _k, r in snap.scan("items") if r["kind"] == "request"}
    assert requests and set(requests.values()) <= {"answered", "recovered"}, requests   # whole and answered, or…
    assert all(f"conv:failed:{rid}" in second.owed.rows for rid, st in requests.items() if st == "recovered")
    # …its words died with the process: it is never an empty item for the model, and he is owed «I lost that»
    said = [o.text for o in first.mouth.orders + second.mouth.orders]
    assert said and all(t.startswith("w-told ") and t != "w-told " or t == "failed:restart" for t in said)
    assert not snap.scan("voice_open", states=("open",)), "a voice was left open after the restart"
    assert all(p["trace"] for _k, _lab, p in first.tel.events + second.tel.events), "an event outside any flow"
    assert audit(snap, clock.now_ms(), second.conv.cfg, drained=True) == []
    second.store.close()
    first.store.close()


def test_a_voice_cut_by_a_restart_is_ended_incomplete_with_its_event_and_asked_again(tmp_path):
    """R3-B1: the process dies while the person speaks; the new one ends that voice incomplete — reason `restart`, its
    event — and he is owed «I lost that» (its words died with the process: an entry with no words is never an item for
    the model, B8e); a text typed behind the dead voice is not left waiting for it."""
    from conversation.ear import signals as S
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    first.conv.hear(S.VadEdge("d1", "rise", 10))
    first.conv.hear(S.WordSpan("d1", 1, 1, False, (("w1", 10, 150, 1.0),), (10, 150)))
    first.conv.hear(S.TypedSubmit("d2", "c1", "w9", 200))                  # waits behind the open voice
    first.store.close()                                                    # the process is gone, mid-sentence
    second = Process(path, clock, tools)
    restarted = [p for k, lab, p in second.tel.events if k == "conv_ear" and lab == "incomplete"]
    assert [(p["reason"], p["refs"]["iv"]) for p in restarted] == [("restart", "iv_000001")]
    _drain(second, clock)
    said = second.mouth.orders
    assert "w-told iv_000002" in [o.text for o in said]                    # the text is answered…
    prompt = second.model.calls[0].prompt.input
    assert "iv_000001" not in prompt and "w9" in prompt                    # …the voice's words died: never an item
    assert "conv:failed:r_iv_000001" in second.owed.rows                   # …and he is owed «I lost that»
    second.store.close()


RESERVATION_CASES = [(pt, when) for pt in (Point.RESERVE, Point.SUBMIT, Point.PROVIDER, Point.RECEIPT)
                     for when in ("before", "after")
                     if not (pt is Point.SUBMIT and when == "after") and not (pt in (Point.PROVIDER, Point.RECEIPT)
                                                                             and when == "before")]


@pytest.mark.parametrize("point,when", RESERVATION_CASES, ids=[f"{p.value}-{w}" for p, w in RESERVATION_CASES])
def test_a_crash_at_a_reservation_point_never_sends_twice(tmp_path, point, when):
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    _speak(first, clock)
    with inject(point, when, tools=tools) as fired:
        with pytest.raises(Crash):
            _act(first)
    assert fired["n"] == 1, "the armed point was never reached by the reservation"
    second = Process(path, clock, tools)
    _act(second)
    _drain(second, clock)
    calls = Counter(eid for _name, _args, eid in tools.calls if eid)
    assert all(n == 1 for n in calls.values()), f"an effect reached the provider twice: {calls}"
    snap = second.store.snapshot(ACCT)
    items = [r for _k, r in snap.scan("items")]
    assert not [r["id"] for r in items if r["kind"] == "request" and r["state"] == "open"], "a request never ended"
    assert audit(snap, clock.now_ms(), second.conv.cfg, drained=True) == []
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

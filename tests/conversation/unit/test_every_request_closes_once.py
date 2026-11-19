"""I9 + N1: every request ends exactly once, and replacing a run never replaces the request (node 13.9).

The provider closes the sentence at a pause and the person goes on while the model is already running: the run is
superseded at its checkpoint, the request stays OPEN, and the next run receives it — with the whole sentence, in one
entry — and answers it: one `conv_close/answered`, not two. Every way a request can end says so once (answered, a
deliberate silence, a provider failure, a stop); a request nobody ran past the liveness budget is closed `stalled`
by the sweep, once, however many sweeps follow.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.ear import signals as S
from conversation.ports import Command, Done, Failed
from conversation.testing.scripted_model import reply
from conversation.types import ControlOp, ItemKind
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.inboxkit import control


def _continue(h: Harness, done: list) -> None:
    """While the model runs, the person goes on with the sentence the provider closed (once)."""
    if done:
        return
    done.append(True)
    t = h.clock.mono + 50
    ws = h.words(["w5", "w6"], t)
    h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 99, 1, True, ws, (t, ws[-1][2])),
           S.VadEdge("d1", "fall", ws[-1][2] + 10), h.beats(ws[-1][2], ws[-1][2] + 300),
           S.EotHint("d1", "flux", "end", .9, ws[-1][2] + 300))


def test_a_superseded_run_leaves_the_request_open_and_the_next_run_answers_it_once(store):
    h = Harness(store)
    done: list = []
    h.model.script["iv_000001"] = [[lambda: _continue(h, done), reply("w90"), Done()]]
    h.utter([(["w1", "w2", "w3"], 0)])
    h.pump()
    assert h.tel.labels("conv_run").count("conv_run/started") == 2
    assert h.tel.labels("conv_run").count("conv_run/superseded") == 1
    inputs = [c.prompt.input for c in h.model.calls]
    assert "«w1 w2 w3»" in inputs[0] and inputs[1].count("[iv_000001") == 1 and "«w1 w2 w3 w5 w6»" in inputs[1]
    assert [lab for lab, _ in h.closes()] == ["answered"]
    req = h.conv.book.snapshot().get("items", "r_iv_000001")
    assert req["state"] == "answered" and len(h.mouth.orders) == 1


def test_every_way_a_request_ends_says_so_once(store):
    h = Harness(store)
    stop = control(ControlOp.STOP, 0, "k1", endpoint="d1")
    plan = [[reply("w1"), Done()], [Command("no_reply", {"reason": "nothing_to_add"}), Done()],
            [Failed("timeout", "provider")], [lambda: h.conv.give(stop), reply("w4"), Done()]]
    # a run on a recovery entry (no intervention of the person) just tells it; the plan is for his entries
    h.model.default = lambda ids: plan.pop(0) if ids and ids[0].startswith("iv") else [reply("w-told"), Done()]
    for n in range(1, 5):
        h.typed(f"w{n}", h.clock.mono + 1000, cid=f"c{n}")
        h.at(h.clock.mono + 1000)
        h.pump()
    assert [(lab, p.get("reason")) for lab, p in h.closes()] == [
        ("answered", None), ("silent", "nothing_to_add"), ("recovered", "provider:timeout"), ("silent", "stopped")]
    assert len({p["refs"]["req"] for _lab, p in h.closes()}) == 4


def test_a_request_nobody_ran_is_closed_stalled_once(store):
    h = Harness(store, config=Config(liveness_ms=5000))
    with h.conv.book.tx() as b:
        b.open(ItemKind.REQUEST, "r_orphan", data={"req": "r_orphan"})
    h.at(4999)
    h.pump()
    assert h.closes() == []
    for t in (5000, 6000, 60_000):
        h.at(t)
        h.pump()
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("stalled", "stalled")]


def test_m7_a_request_is_opened_when_its_entry_is_accepted(store):
    """Liveness counts from acceptance: a sentence that never got a run is still a request the sweep closes."""
    h = Harness(store, config=Config(liveness_ms=5000))
    h.live = False
    h.utter([(["w1"], 0)])
    req = h.conv.book.snapshot().get("items", "r_iv_000001")
    assert req is not None and req["state"] == "open" and h.model.calls == []
    h.at(h.clock.mono + 5000)
    h.conv.sweep()
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("stalled", "stalled")]


def test_b3_a_hung_model_times_out_and_the_request_recovers_visibly(store):
    import asyncio

    from conversation.ports import Done

    class Hung:
        calls: list = []

        async def stream(self, prompt, tools, *, run_id, model_id):
            self.calls.append(prompt)
            if len(self.calls) == 1:
                await asyncio.sleep(10)                         # the provider holds the stream and sends nothing
            yield reply("w-recovery")
            yield Done()

    h = Harness(store, config=Config(model_first_ms=30))
    h.conv.model = Hung()
    h.utter([(["w1"], 0)])
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "provider:timeout")]
    assert "conv_run/port_slow" in h.tel.labels()
    assert [o.text for o in h.mouth.orders] == ["w-recovery"]       # the person hears it, in the model's words
    assert "«failed:provider:timeout»" in h.conv.model.calls[1].input


def test_b3_the_sweep_closes_the_request_of_a_run_in_course_and_stops_it(store):
    h = Harness(store, config=Config(liveness_ms=5000))

    def stall():
        h.at(h.clock.mono + 6000)
        h.conv.sweep()                                          # the sweep runs on its own timer, not inside pump

    h.model.script["iv_000001"] = [[stall, reply("w9"), Done()]]
    h.utter([(["w1"], 0)])
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("stalled", "stalled")]
    assert not h.mouth.orders and "conv_run/cancelled" in h.tel.labels()


def test_b6_a_tool_that_raises_ends_the_run_visibly_and_accounts_its_batch(store):
    from conversation.inbox.accounting import audit
    from conversation.ports import ToolCall
    h = Harness(store)
    h.tools.raises["search"] = ValueError("adapter broke")
    h.model.default = lambda ids: ([ToolCall("c", "search", {"q": "w1"}), Done()] if ids[0].startswith("iv")
                                   else [reply("w-told"), Done()])
    h.utter([(["w1"], 0)])
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "ValueError")]
    rows = [r for _k, r in store.snapshot("acct-test").scan("inbox") if r["kind"] == "user.utterance"]
    assert [r["outcome"] for r in rows] == ["failed"]
    assert audit(store.snapshot("acct-test"), h.clock.now_ms(), h.conv.cfg, drained=True) == []
    assert [o.text for o in h.mouth.orders] == ["w-told"]

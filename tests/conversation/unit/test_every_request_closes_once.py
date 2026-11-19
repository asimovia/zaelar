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
    h.model.default = lambda ids: plan.pop(0)
    for n in range(1, 5):
        h.typed(f"w{n}", h.clock.mono + 1000, cid=f"c{n}")
        h.at(h.clock.mono + 1000)
        h.pump()
    assert [(lab, p.get("reason")) for lab, p in h.closes()] == [
        ("answered", None), ("silent", "nothing_to_add"), ("failed", "provider:timeout"), ("silent", "stopped")]
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

"""The policy table is total and keeps three operations apart (node 13.8, D3, §7).

Every (input, state) pair has a cell; a stop never cancels a task (no cell holds a task cancel, and the stop rows hold
SILENCE and CANCEL_RUN only); SILENCE, CANCEL_RUN and a task's cancel are different things; a control never waits;
a text while we speak silences us (CRIT-V22, PA-11) and then supersedes or follows up. And the table is what the
manager does: a stop during a run silences and cancels the RUN, and the task the person had going is still running.
"""
from __future__ import annotations

from conversation.manager import policy
from conversation.manager.policy import TABLE, Column, Input
from conversation.ports import Done, ToolCall
from conversation.testing.scripted_model import reply
from conversation.types import ControlOp, Op
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.inboxkit import control

WAITS = {Op.JOIN, Op.WHEN_IDLE, Op.HOLD_BEHIND, Op.WAIT_FOCUS, Op.WAIT_AGAIN, Op.COALESCE, Op.AT_CHECKPOINT}


def test_every_pair_has_a_cell():
    missing = [(i, c) for i in Input for c in Column if c not in TABLE.get(i, {}) or not TABLE[i][c]]
    assert not missing


def test_stop_silences_and_cancels_the_run_never_a_task_and_never_waits():
    for col, ops in TABLE[Input.STOP].items():
        assert Op.SILENCE in ops and set(ops) <= {Op.SILENCE, Op.CANCEL_RUN}, col
        if col not in (Column.IDLE, Column.COLLECTING):
            assert Op.CANCEL_RUN in ops, col
    for row in (Input.STOP, Input.BY_ID):
        assert not any(set(ops) & WAITS for ops in TABLE[row].values()), row
    assert Op.SILENCE is not Op.CANCEL_RUN
    assert not any("task" in op.value for ops in (o for r in TABLE.values() for o in r.values()) for op in ops)


def test_new_input_while_we_speak_silences_then_supersedes_or_follows_up():
    for row in (Input.UTTERANCE, Input.TEXT):
        assert TABLE[row][Column.SPEAK_UNCLAIMED] == (Op.SILENCE, Op.SUPERSEDE)
        assert TABLE[row][Column.SPEAK_CLAIMED] == (Op.SILENCE, Op.FOLLOW_UP)
        assert TABLE[row][Column.RUN_UNCLAIMED] == (Op.SUPERSEDE,) and TABLE[row][Column.RUN_CLAIMED] == (
            Op.FOLLOW_UP,)


def test_a_worker_question_never_takes_the_focus_while_the_person_speaks(store):
    from conversation import envelopes as E
    from conversation.types import EnvelopeKind, MgrState, WorkerUpdate
    q = E.make(EnvelopeKind.WORKER_UPDATE, E.WorkerBody("t1", WorkerUpdate.QUESTION, "w1", question_id="q1"),
               producer="worker:t1", producer_id="1", account="a", onset_ms=0, sealed_ms=0)
    assert policy.decide(q, MgrState.IDLE) == (Op.SURFACE_NOW,)
    assert policy.decide(q, MgrState.IDLE, person_speaking=True) == (Op.WAIT_FOCUS,)


def test_a_stop_during_a_run_silences_and_cancels_the_run_and_the_task_goes_on(store):
    h = Harness(store)
    with h.conv.book.tx() as b:
        from conversation.types import ItemKind
        b.open(ItemKind.TASK, "t1", owner="worker:t1")
        b.move("t1", "running")
    stop = control(ControlOp.STOP, 0, "k-stop", endpoint="d1")
    h.model.script["iv_000001"] = [[lambda: h.conv.give(stop), ToolCall("c", "search", {"q": "w1"}),
                                    reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.pump()
    assert not h.mouth.orders and not h.tools.calls                   # cancelled at the checkpoint, before the tool
    assert ("stop", None, "stop") in h.mouth.calls
    assert "conv_run/cancelled" in h.tel.labels()
    assert h.conv.book.snapshot().get("items", "t1")["state"] == "running"
    assert [lab for lab, _ in h.closes()] == ["silent"]


def test_a_continuation_that_closes_mid_run_substitutes_it_and_the_model_hears_both_once(store):
    """No reopen: the provider closed «w1 w2», the model starts, the person goes on and that continuation closes — a
    new intervention that amends the first. The run is substituted at its checkpoint and the next one carries both:
    the model is called once more, with every word, and nothing is said before."""
    from conversation.ear import signals as S
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply

    h = Harness(store)
    went_on: list = []

    def go_on():
        if went_on:
            return
        went_on.append(True)
        h.utter([(["w3", "w4"], 0)])

    h.model.script["iv_000001"] = [[go_on, reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    assert len(h.model.calls) == 2 and len(h.mouth.orders) == 1
    last = h.model.calls[1].prompt.input
    assert "«w1 w2»" in last and "amends iv_000001] «w3 w4»" in last
    assert [lab for lab, _ in h.closes()] == ["answered", "answered"]


def test_a_cough_after_the_close_is_discarded_and_answers_nothing(store):
    from conversation.ear import signals as S
    h = Harness(store)
    h.live = False
    t = h.utter([(["w1"], 0)])
    h.hear(S.VadEdge("d1", "rise", t + 50), S.VadEdge("d1", "fall", t + 200), S.Tick(t + 3000))
    assert "conv_ear/discarded" in h.tel.labels()
    h.pump()
    assert len(h.model.calls) == 1 and [lab for lab, _ in h.closes()] == ["answered"]

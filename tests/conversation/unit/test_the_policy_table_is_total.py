"""The policy table is total — seven rows, four columns, 28 cells — and keeps three operations apart (node 13.8).

Three states (free, running, speaking), whether the run claimed an effect is a column of the table and not a state,
and eleven operations, every one used. Every (input, column) pair has its cell; only a line owed and a voice that
ended with no word have empty cells, on purpose: while the manager is not free the line waits in its own ledger, and a
wordless voice changes nothing (when free, it resumes the line it cut). A stop never cancels a task (the stop rows hold
SILENCE and CANCEL_RUN only); a control never waits; a closed entry while we speak silences us and runs. And the table
is what the manager does: a stop during a run silences and cancels the RUN, and the task the person had going is still
running; a line owed waits behind the run and is said after its line.
"""
from __future__ import annotations

from conversation.manager import policy
from conversation.manager.policy import IN_ITS_LEDGER, TABLE, Column, Input
from conversation.ports import Done, ToolCall
from conversation.testing.scripted_model import reply
from conversation.types import ControlOp, MgrState, Op
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.inboxkit import control

WAITS = {Op.FOLLOW_UP, Op.HOLD_FOR_VOICE, Op.ACTIONS_WAIT, Op.WAIT_BEHIND_VOICE}


def test_three_states_eight_rows_four_columns_eleven_operations():
    assert [m.value for m in MgrState] == ["idle", "running", "speaking"]
    assert len(Input) == 8 and len(Column) == 4 and len(Op) == 11
    assert {op for row in TABLE.values() for ops in row.values() for op in ops} == set(Op)   # none unused


def test_every_pair_has_a_cell_and_only_a_line_owed_or_a_wordless_voice_does_nothing_when_busy():
    assert sorted((i.value, c.value) for i in TABLE for c in TABLE[i]) == sorted(
        (i.value, c.value) for i in Input for c in Column)
    empty = [(i, c) for i in Input for c in Column if not TABLE[i][c]]
    busy = (Column.RUN_NO_EFFECT, Column.RUN_EFFECT, Column.SPEAKING)
    assert empty == [(i, c) for i in (Input.OWED, Input.DISCARDED, Input.EVENT) for c in busy]
    assert TABLE[Input.EVENT][Column.IDLE] == (Op.RUN,)          # an event runs only when free: it waits for him
    assert TABLE[Input.DISCARDED][Column.IDLE] == (Op.RESUME_LINE,)
    assert TABLE[Input.OWED][Column.IDLE] == (Op.SAY_OWED,) and IN_ITS_LEDGER == ()


def test_stop_silences_and_cancels_the_run_never_a_task_and_never_waits():
    for col, ops in TABLE[Input.STOP].items():
        assert Op.SILENCE in ops and set(ops) <= {Op.SILENCE, Op.CANCEL_RUN}, col
        assert (Op.CANCEL_RUN in ops) == (col in (Column.RUN_NO_EFFECT, Column.RUN_EFFECT)), col
    for row in (Input.STOP, Input.BY_ID):
        assert not any(set(ops) & WAITS for ops in TABLE[row].values()), row
    assert not any("task" in op.value for ops in (o for r in TABLE.values() for o in r.values()) for op in ops)


def test_an_entry_supersedes_a_run_with_no_effect_follows_one_with_and_silences_our_voice():
    assert TABLE[Input.ENTRY] == {Column.IDLE: (Op.RUN,), Column.RUN_NO_EFFECT: (Op.SUPERSEDE,),
                                  Column.RUN_EFFECT: (Op.FOLLOW_UP,), Column.SPEAKING: (Op.SILENCE, Op.RUN)}
    assert TABLE[Input.INCOMPLETE][Column.SPEAKING] == (Op.FOLLOW_UP,)    # it asks for the end after our line


def test_a_voice_starting_holds_the_run_only_where_it_has_not_acted_and_never_touches_our_voice():
    onset = TABLE[Input.ONSET]
    assert Op.HOLD_FOR_VOICE in onset[Column.RUN_NO_EFFECT] and Op.HOLD_FOR_VOICE not in onset[Column.RUN_EFFECT]
    assert all(Op.WAIT_BEHIND_VOICE in ops for ops in onset.values())
    assert not any({Op.SILENCE, Op.CANCEL_RUN} & set(ops) for ops in onset.values())
    assert policy.column(MgrState.RUNNING, True) is Column.RUN_EFFECT
    assert policy.column(MgrState.RUNNING, False) is Column.RUN_NO_EFFECT


def test_a_line_owed_waits_behind_the_run_and_is_said_after_its_line(store):
    h = Harness(store, grace=False)
    h.model.script["iv_000001"] = [[lambda: h.owed.add("n1", "w5"), reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.pump()
    assert [o.text for o in h.mouth.orders] == ["w9", "w5"]
    assert h.owed.rows["n1"]["state"] == "spoken"


def test_a_stop_during_a_run_silences_and_cancels_the_run_and_the_task_goes_on(store):
    from conversation.testing.fakes import FakeTasks
    tasks = FakeTasks()
    h = Harness(store, tasks=tasks)                                     # the person has a task of the host going
    stop = control(ControlOp.STOP, 0, "k-stop", endpoint="d1")
    h.model.script["iv_000001"] = [[lambda: h.conv.give(stop), ToolCall("c", "search", {"q": "w1"}),
                                    reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    h.pump()
    assert not h.mouth.orders and not h.tools.calls                   # cancelled at the checkpoint, before the tool
    assert ("stop", None, "stop") in h.mouth.calls
    assert "conv_run/cancelled" in h.tel.labels()
    assert tasks.cancelled == []                                        # the task goes on
    assert [lab for lab, _ in h.closes()] == ["silent"]


def test_a_continuation_that_closes_mid_run_substitutes_it_and_the_model_hears_both_once(store):
    """No reopen: the provider closed «w1 w2», the model starts, the person goes on and that continuation closes — a
    new intervention that amends the first. The run is substituted at its checkpoint and the next one carries both:
    the model is called once more, with every word, and nothing is said before."""
    from conversation.ear import signals as S
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply

    h = Harness(store, grace=False)
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


def test_a_text_typed_while_a_voice_is_open_waits_behind_it_and_both_go_in_one_run(store):
    """Onset × any column notes the open voice: a text the person types on another device after starting to speak
    waits behind that voice, and the run hears both, in the order they were begun."""
    from conversation.ear import signals as S
    h = Harness(store)
    ws = h.words(["w1", "w2"], 100)
    h.hear(S.VadEdge("d1", "rise", 100), S.WordSpan("d1", 1, 1, False, ws, (100, ws[-1][2])), h.beats(100, 1900))
    h.typed("w9", 600)
    h.at(2000).pump()
    assert not h.model.calls                                            # the text waits behind the open voice
    h.hear(S.WordSpan("d1", 1, 2, True, ws, (100, ws[-1][2])), S.VadEdge("d1", "fall", 2010), h.beats(2010, 2400),
           S.EotHint("d1", "flux", "end", .9, 2400))
    h.pump()
    assert len(h.model.calls) == 1
    said = h.model.calls[0].prompt.input
    assert said.index("w1 w2") < said.index("w9")

"""THE policy table: what the manager DOES with each kind of input in each of its states. Data, not code.

Eight rows — kinds of input, classified by envelope kind and declared fields, never by what was said — and four
columns: free, a run that has not claimed an effect, a run that has, and speaking. 32 cells (node 13.8). Three operations that are never confused: SILENCE stops our voice, CANCEL_RUN drops the run, and
cancelling a TASK is a tool the model calls or a button by id — no cell of this table cancels a task. A stop is a
`user.control(stop)` from a button, or a stop order the model chose from his words (`commands.Stop`, `stop.py`); this
package reads no words for it. Controls never wait.

The one cell that depends on the input's data: a voice that starts during a run that has not claimed an effect.
Its actions wait (ACTIONS_WAIT) and, if it is the same device as the batch's last entry and inside the window of it,
the run stops and its batch waits for that voice (HOLD_FOR_VOICE) — device and time are fields of the signal, not
words. A line owed waits in its own ledger while the manager is not free: those cells are empty on purpose
(`IN_ITS_LEDGER`); so does an EVENT of the world (R-2): free, it runs on its own; otherwise it waits in the inbox, never
joining nor replacing a batch of his. A voice that cut our line and ended with no word (a breath, a noise) resumes that line once, from
the last sentence heard (`RESUME_LINE`) — only when free; with a run in course it changes nothing.
"""
from __future__ import annotations

from enum import Enum

from conversation import envelopes as E
from conversation.ear.signals import Onset, VoiceDiscarded
from conversation.types import ControlOp, Coverage, EnvelopeKind, MgrState, Op


class Input(Enum):
    ONSET = "onset"
    ENTRY = "entry"                    # a closed entry: a whole utterance, or a text
    INCOMPLETE = "incomplete"          # an utterance that ended without its final words: the run asks for the end
    STOP = "stop"
    BY_ID = "by_id"
    OWED = "owed"                      # a line the engine owes the person, waiting in its own ledger
    DISCARDED = "discarded"            # a voice that ended with no word
    EVENT = "event"                    # an event of the world, already routed: it waits for the manager to be free


class Column(Enum):
    IDLE = "idle"
    RUN_NO_EFFECT = "run_no_effect"
    RUN_EFFECT = "run_effect"
    SPEAKING = "speaking"


I, RN, RE, SP = Column.IDLE, Column.RUN_NO_EFFECT, Column.RUN_EFFECT, Column.SPEAKING
O = Op
IN_ITS_LEDGER: tuple[Op, ...] = ()


def _row(idle, run_no_effect, run_effect, speaking) -> dict:
    return {I: idle, RN: run_no_effect, RE: run_effect, SP: speaking}


TABLE: dict[Input, dict[Column, tuple[Op, ...]]] = {
    Input.ONSET: _row((O.WAIT_BEHIND_VOICE,), (O.WAIT_BEHIND_VOICE, O.ACTIONS_WAIT, O.HOLD_FOR_VOICE),
                      (O.WAIT_BEHIND_VOICE, O.ACTIONS_WAIT), (O.WAIT_BEHIND_VOICE,)),
    Input.ENTRY: _row((O.RUN,), (O.SUPERSEDE,), (O.FOLLOW_UP,), (O.SILENCE, O.RUN)),
    Input.INCOMPLETE: _row((O.RUN,), (O.SUPERSEDE,), (O.FOLLOW_UP,), (O.FOLLOW_UP,)),
    Input.STOP: _row((O.SILENCE,), (O.SILENCE, O.CANCEL_RUN), (O.SILENCE, O.CANCEL_RUN), (O.SILENCE,)),
    Input.BY_ID: _row((O.BY_ID,), (O.BY_ID,), (O.BY_ID,), (O.BY_ID,)),
    Input.OWED: _row((O.SAY_OWED,), IN_ITS_LEDGER, IN_ITS_LEDGER, IN_ITS_LEDGER),
    Input.DISCARDED: _row((O.RESUME_LINE,), (), (), ()),
    Input.EVENT: _row((O.RUN,), IN_ITS_LEDGER, IN_ITS_LEDGER, IN_ITS_LEDGER),   # never joins nor replaces a run of his
}


def classify(item: E.Envelope | Onset | VoiceDiscarded | None) -> Input:
    """`None` is the line owed: the manager asks its ledger for it, nobody hands it in."""
    if item is None:
        return Input.OWED
    if isinstance(item, Onset):
        return Input.ONSET
    if isinstance(item, VoiceDiscarded):
        return Input.DISCARDED
    k = item.kind
    if k is EnvelopeKind.USER_UTTERANCE:
        return Input.ENTRY if item.body.coverage is Coverage.FULL else Input.INCOMPLETE
    if k is EnvelopeKind.USER_TEXT:
        return Input.ENTRY
    if k is EnvelopeKind.USER_CONTROL:
        return Input.STOP if item.body.op is ControlOp.STOP else Input.BY_ID
    if k is EnvelopeKind.EVENT:
        return Input.EVENT
    raise ValueError(f"no policy row for {k}")


def column(state: MgrState, claimed: bool) -> Column:
    if state is MgrState.IDLE:
        return Column.IDLE
    if state is MgrState.SPEAKING:
        return Column.SPEAKING
    return Column.RUN_EFFECT if claimed else Column.RUN_NO_EFFECT


def decide(item: E.Envelope | Onset | VoiceDiscarded | None, state: MgrState, *,
           claimed: bool = False) -> tuple[Op, ...]:
    return TABLE[classify(item)][column(state, claimed)]

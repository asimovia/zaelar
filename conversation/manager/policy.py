"""THE policy table (§7): what the manager DOES with each kind of input in each of its states. Data, not code.

Rows are kinds of input (classified by envelope kind and declared fields — never by what was said); columns are the
manager's states, with «running» and «speaking» split by whether the run already claimed an effect. Every cell is
filled (node 13.8). Three operations that are never confused (D3): SILENCE stops our voice, CANCEL_RUN drops the run,
and cancelling a TASK is a tool the model calls or a button by id — no cell of this table cancels a task. A stop is a
`user.control(stop)` from a button or from the safety detector outside the package; this package reads no words for
it (PA-5). Controls never wait.
"""
from __future__ import annotations

from enum import Enum

from conversation import envelopes as E
from conversation.ear.signals import Onset
from conversation.types import ControlOp, EnvelopeKind, IvState, MgrState, Op, Surfacing, WorkerUpdate


class Input(Enum):
    ONSET = "onset"
    UTTERANCE = "utterance"
    TEXT = "text"
    STOP = "stop"
    BY_ID = "by_id"
    INCOMPLETE = "incomplete"
    WORKER_QUESTION = "worker_question"
    WORKER_PROGRESS = "worker_progress"
    WORKER_RESULT = "worker_result"
    CONTACT = "contact"
    REMINDER = "reminder"
    VOICE_STATE = "voice_state"        # opened / tentative / extended / discarded: the inbox's, nothing to do here


class Column(Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    RUN_UNCLAIMED = "running_unclaimed"
    RUN_CLAIMED = "running_claimed"
    SPEAK_UNCLAIMED = "speaking_unclaimed"
    SPEAK_CLAIMED = "speaking_claimed"


I, C, RU, RC, SU, SC = (Column.IDLE, Column.COLLECTING, Column.RUN_UNCLAIMED, Column.RUN_CLAIMED,
                        Column.SPEAK_UNCLAIMED, Column.SPEAK_CLAIMED)
O = Op


def _row(idle, collecting, run_u, run_c, speak_u, speak_c) -> dict:
    return {I: idle, C: collecting, RU: run_u, RC: run_c, SU: speak_u, SC: speak_c}


TABLE: dict[Input, dict[Column, tuple[Op, ...]]] = {
    Input.ONSET: _row((O.FIX_FOCUS,), (O.FIX_FOCUS,), (O.FIX_FOCUS, O.HOLD_ACTIONS), (O.FIX_FOCUS, O.HOLD_ACTIONS),
                      (O.FIX_FOCUS, O.DUCK), (O.FIX_FOCUS, O.DUCK)),
    Input.UTTERANCE: _row((O.RUN_NOW,), (O.JOIN,), (O.SUPERSEDE,), (O.FOLLOW_UP,), (O.SILENCE, O.SUPERSEDE),
                          (O.SILENCE, O.FOLLOW_UP)),
    Input.TEXT: _row((O.RUN_NOW,), (O.JOIN,), (O.SUPERSEDE,), (O.FOLLOW_UP,), (O.SILENCE, O.SUPERSEDE),
                     (O.SILENCE, O.FOLLOW_UP)),
    Input.STOP: _row((O.SILENCE,), (O.SILENCE,), (O.SILENCE, O.CANCEL_RUN), (O.SILENCE, O.CANCEL_RUN),
                     (O.SILENCE, O.CANCEL_RUN), (O.SILENCE, O.CANCEL_RUN)),
    Input.BY_ID: _row((O.BY_ID,), (O.BY_ID,), (O.BY_ID,), (O.BY_ID,), (O.BY_ID,), (O.BY_ID,)),
    Input.INCOMPLETE: _row((O.RUN_NOW,), (O.JOIN,), (O.AT_CHECKPOINT,), (O.FOLLOW_UP,), (O.WHEN_IDLE,),
                           (O.WHEN_IDLE,)),
    Input.WORKER_QUESTION: _row((O.SURFACE_NOW,), (O.WAIT_FOCUS,), (O.AT_CHECKPOINT,), (O.AT_CHECKPOINT,),
                                (O.WHEN_IDLE,), (O.WHEN_IDLE,)),
    Input.WORKER_PROGRESS: _row(*([(O.COALESCE,)] * 6)),
    Input.WORKER_RESULT: _row(*([(O.WHEN_IDLE,)] * 6)),
    Input.CONTACT: _row(*([(O.WHEN_IDLE,)] * 6)),
    Input.REMINDER: _row((O.SURFACE_NOW,), (O.SURFACE_NOW,), (O.WHEN_IDLE,), (O.WHEN_IDLE,), (O.WHEN_IDLE,),
                         (O.WHEN_IDLE,)),
    Input.VOICE_STATE: _row(*([(O.NONE,)] * 6)),
}


def classify(item: E.Envelope | Onset) -> Input:
    if isinstance(item, Onset):
        return Input.ONSET
    k = item.kind
    if k is EnvelopeKind.USER_UTTERANCE:
        return Input.UTTERANCE
    if k is EnvelopeKind.USER_TEXT:
        return Input.TEXT
    if k is EnvelopeKind.USER_CONTROL:
        return Input.STOP if item.body.op is ControlOp.STOP else Input.BY_ID
    if k is EnvelopeKind.INTERVENTION_STATE:
        return Input.INCOMPLETE if item.body.state is IvState.INCOMPLETE else Input.VOICE_STATE
    if k is EnvelopeKind.WORKER_UPDATE:
        t = item.body.type
        return (Input.WORKER_QUESTION if t is WorkerUpdate.QUESTION else
                Input.WORKER_PROGRESS if t is WorkerUpdate.PROGRESS else Input.WORKER_RESULT)
    if k is EnvelopeKind.CONTACT_MESSAGE:
        return Input.CONTACT
    return Input.REMINDER


def column(state: MgrState, claimed: bool) -> Column:
    if state is MgrState.IDLE:
        return Column.IDLE
    if state is MgrState.COLLECTING:
        return Column.COLLECTING
    if state is MgrState.SPEAKING:
        return Column.SPEAK_CLAIMED if claimed else Column.SPEAK_UNCLAIMED
    return Column.RUN_CLAIMED if claimed or state is MgrState.RUNNING_CLAIMED else Column.RUN_UNCLAIMED


def decide(item: E.Envelope | Onset, state: MgrState, *, claimed: bool = False,
           person_speaking: bool = False) -> tuple[Op, ...]:
    ops = TABLE[classify(item)][column(state, claimed)]
    if isinstance(item, E.Envelope) and item.kind is EnvelopeKind.SYSTEM_REMINDER and \
            item.surfacing is Surfacing.WHEN_IDLE and ops == (O.SURFACE_NOW,):
        return (O.WHEN_IDLE,)                       # the reminder's own declared surfacing
    if person_speaking and ops == (O.SURFACE_NOW,) and classify(item) is Input.WORKER_QUESTION:
        return (O.WAIT_FOCUS,)                      # never take the focus while they are speaking (N2)
    return ops

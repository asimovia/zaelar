"""V2-224 — «did I already tell it?» was a deduction made by the model, and it had to be a fact supplied by us.

V2-221 added the unconditional instruction («TELL IT THIS TURN») and it worked: the harness measured 2 out of 2 turns
saying it, on turn 2, without anyone asking. But it put the anti-repetition rule INSIDE the same sentence
—«if you already told it in an earlier turn, do not repeat it»— and this was measured in TWO rounds of the SAME commit with
opposite results:

    round 5 → it said it on turn 2 and REPETED it on 5, 6, 7, 8, and 9.            (the V2-189 broken record)
    round 6 → it said it on turn 2 and then DENIED it for seven turns: «I am still working on it»,
              «Give me a moment», «I am relaunching it now».

Same commit, same clause, opposite failures. That is not a wrongly set threshold: it is that the «already told it»
record did not govern the decision. In one round it did not find it and repeated it; in the other it found it and fell
completely SILENT — and silencing the repetition is not silencing the state.

We know how many turns have carried that ending forward. So it is counted, and each turn receives ONE
instruction: the first time, say it; from then on, do not repeat it BUT keep it dead, and the reassuring phrases
remain forbidden.
"""
import pytest

from nucleo import dispatch as d


class _Rec:
    def __init__(self, tid, goal, status="error", ok=False, summary=""):
        self.task_id, self.goal, self.status, self.ok, self.result_summary = tid, goal, status, ok, summary


@pytest.fixture(autouse=True)
def _clean():
    e = dict(d._ENDED_SESSIONS)
    d._ENDED_SESSIONS.clear()
    yield
    d._ENDED_SESSIONS.clear(); d._ENDED_SESSIONS.update(e)


GOAL = "Busca hoteles de 4 estrellas en Sevilla"


FAILED = [{"id": "1", "goal": GOAL, "status": "error", "ok": False, "summary": "", "ago_s": 5, "told": 0}]


def test_a_fresh_death_starts_at_zero():
    d._remember_ended(_Rec("1", GOAL))
    assert d.recently_ended_sessions()[0]["told"] == 0


def test_marking_an_id_that_no_longer_exists_is_harmless():
    """The record expires after 5 minutes; the turn that carried it forward may arrive late."""
    d.mark_death_reported(["no-existe", ""])

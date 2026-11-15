"""The driver walks a programme to its report and calls each hand only in its step (V2-909, `nucleo/play/run.py`).

Resolve, then his consent when it is owed, then the executor, then the look at the end state, then ONE report. A
refused consent executes nothing; an executor that fails or raises is never followed by a look; an executor that does
not return in time ends `unverified`; a missing slot is asked once and his answer resumes the same programme.

Disarm: the driver looks at the end state while the executor is still out → red.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib
import shutil

import pytest

from nucleo.play import run as driver
from nucleo.play import state as st

ROOT = pathlib.Path(__file__).resolve().parents[4]
HIS = {"recipient": {"value": "R", "source": "his"}, "text": {"value": "hello", "source": "his"}}


class Hands:
    def __init__(self, *, slots=None, missing=None, consent="yes", result=None, landed=True, raises=(), slow=()):
        self.calls, self.said = [], []
        self.slots, self.missing, self._consent = slots or HIS, missing, consent
        self.result, self.landed, self.raises, self.slow = result or {"ok": True}, landed, raises, slow

    async def _do(self, name):
        self.calls.append(name)
        if name in self.slow:
            await asyncio.sleep(3600)
        if name in self.raises:
            raise RuntimeError(name)

    async def resolve(self, state):
        await self._do("resolve")
        if self.missing and self.missing not in state["slots"]:
            return {"missing": self.missing}
        return {"slots": self.slots}

    async def answer(self, state, slot):
        await self._do("answer")
        return {"slots": {slot: {"value": "whatsapp", "source": "his"}}}

    async def consent(self, state):
        await self._do("consent")
        return self._consent

    async def execute(self, state):
        await self._do("execute")
        return self.result

    async def look(self, state):
        await self._do("look")
        return self.landed

    def say(self, kind, value, state):
        self.said.append((kind, value))


def _go(hands, monkeypatch=None, **prog):
    if monkeypatch is not None:                            # deadlines of a few ms, so a slow hand times out at once
        monkeypatch.setitem(st._TABLE, "deadline_s", {k: 0.02 for k in st._TABLE["deadline_s"]})
    s = st.new("mensajeria", "send_to", {"confirm": False, "leaves": True, "verify": "check", **prog})
    return asyncio.run(driver.run(s, hands))


def test_a_dictated_send_is_resolved_executed_looked_at_and_reported_once():
    h = Hands()
    end = _go(h)
    assert h.calls == ["resolve", "execute", "look"]
    assert (end["step"], end["outcome"]) == ("reported", "done")
    assert h.said == [("announce", ""), ("report", "done")]


def test_a_slot_the_agent_chose_is_confirmed_before_anything_leaves():
    h = Hands(slots={**HIS, "channel": {"value": "email", "source": "agent"}})
    end = _go(h)
    assert h.calls == ["resolve", "consent", "execute", "look"] and end["outcome"] == "done"
    assert [k for k, _ in h.said] == ["confirm", "announce", "report"]


def test_his_no_executes_nothing():
    h = Hands(consent="no")
    end = _go(h, confirm=True)
    assert "execute" not in h.calls and "look" not in h.calls
    assert end["outcome"] == "cancelled" and h.said[-1] == ("report", "cancelled")


def test_a_missing_slot_is_asked_once_and_his_answer_resumes_the_same_programme():
    h = Hands(missing="channel")
    end = _go(h)
    assert h.calls == ["resolve", "answer", "resolve", "execute", "look"]
    assert [s for s in h.said if s[0] == "ask"] == [("ask", "channel")]
    assert end["slots"]["channel"]["value"] == "whatsapp" and end["outcome"] == "done"


@pytest.mark.parametrize("hands,outcome", [
    (dict(result={"ok": False, "error": "refused"}), "failed"),
    (dict(raises=("execute",)), "failed"),
])
def test_an_executor_that_fails_is_never_followed_by_a_look(hands, outcome):
    h = Hands(**hands)
    end = _go(h)
    assert "look" not in h.calls and end["outcome"] == outcome and h.said[-1] == ("report", outcome)


def test_an_executor_that_does_not_return_ends_unverified(monkeypatch):
    h = Hands(slow=("execute",))
    end = _go(h, monkeypatch)
    assert "look" not in h.calls and end["outcome"] == "unverified"


@pytest.mark.parametrize("landed,raises,outcome", [(False, (), "failed"), (None, (), "unverified"),
                                                   (True, ("look",), "unverified")])
def test_the_report_says_what_the_look_found(landed, raises, outcome):
    h = Hands(landed=landed, raises=raises)
    end = _go(h)
    assert end["outcome"] == outcome and h.said[-1] == ("report", outcome)
    assert h.calls.count("look") == (2 if landed is False else 1)     # an absent end state is looked at once more


def test_an_end_state_nobody_can_read_is_never_looked_at_nor_called_done():
    h = Hands()
    end = _go(h, verify="unreadable")
    assert "look" not in h.calls and end["outcome"] == "unverified"


def test_disarmed_a_driver_that_looks_before_the_executor_returned_turns_red():
    """Disarm: the look runs in the `executing` step, before the executor is called."""
    src = ROOT / "nucleo" / "play" / "run.py"
    orig = src.read_text(encoding="utf-8")
    line = "            got, bad = await _call(hands.execute, limits.get(step), state)\n"
    assert line in orig, "the disarm no longer matches nucleo/play/run.py"
    try:
        src.write_text(orig.replace(line, "            await _call(hands.look, None, state)\n" + line), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert "            await _call(hands.look, None, state)\n" in src.read_text(encoding="utf-8")
        importlib.reload(driver)
        with pytest.raises(AssertionError):
            test_a_dictated_send_is_resolved_executed_looked_at_and_reported_once()
        with pytest.raises(AssertionError):
            test_an_executor_that_fails_is_never_followed_by_a_look(dict(raises=("execute",)), "failed")
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(driver)

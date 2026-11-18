"""«Stick to my voice» (V2-651 F1): with the switch on, a turn of ANOTHER voice never reaches the brain.

The browser judges every speech segment against the voice it enrolled first and, while the switch is on, sends each
verdict to the voice process (`zaelar-speaker`) with the switch itself (`zaelar-voicelock`). The attention gate asks
`voice_lock.admit()` before any judge or model. Pinned here:
  · the decision: enrolled voice → kept; another voice → dropped; no enrolment, switch off, or no verdict → kept;
  · a verdict is consumed by the turn that reads it, and one from an earlier utterance does not vote;
  · the gate drops the turn before the attention judge runs, and does not file it as reclaimable room noise;
  · the data channel carries both topics to the module.
Disarms: the decision that keeps everything, and the gate that never asks — each turns a case red.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from voice import voice_lock as VL


@pytest.fixture(autouse=True)
def _clean():
    VL.set_state(False, False)
    yield
    VL.set_state(False, False)


def _run(coro):
    return asyncio.run(coro)


# ── the decision, pure ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_enrolled_voice_passes_and_another_is_dropped():
    assert VL.decide(on=True, enrolled=True, labels=["operator"]) == (True, "operator")
    assert VL.decide(on=True, enrolled=True, labels=["other"]) == (False, "other_voice")
    assert VL.decide(on=True, enrolled=True, labels=["known:ana"]) == (False, "other_voice"), \
        "a known household voice is still not HIS voice"
    assert VL.decide(on=True, enrolled=True, labels=["other", "operator"]) == (True, "operator"), \
        "any segment of his keeps the turn: he spoke over the TV"


def test_no_enrolment_or_switch_off_filters_nothing():
    assert VL.decide(on=True, enrolled=False, labels=["other"]) == (True, "no_enrollment")
    assert VL.decide(on=False, enrolled=True, labels=["other"]) == (True, "off")
    assert VL.decide(on=True, enrolled=True, labels=[]) == (True, "no_verdict"), "no verdict fails OPEN"


# ── the state the data channel feeds ─────────────────────────────────────────────────────────────────────────────
def test_admit_reads_the_turns_verdicts_and_consumes_them():
    VL.set_state(True, True)
    VL.note_verdict("other", now=100.0)
    assert _run(VL.admit(onset=99.8, now=101.0, grace_s=0)) == (False, "other_voice")
    VL.note_verdict("operator", now=102.0)
    assert _run(VL.admit(onset=101.9, now=103.0, grace_s=0)) == (True, "operator")
    assert VL.state()["pending"] == 0, "a verdict is consumed by the turn that read it"


def test_a_verdict_older_than_the_utterance_does_not_vote():
    VL.set_state(True, True)
    VL.note_verdict("other", now=50.0)
    assert _run(VL.admit(onset=60.0, now=61.0, grace_s=0)) == (True, "no_verdict")


def test_a_late_verdict_inside_the_grace_still_decides():
    VL.set_state(True, True)

    async def late():
        async def send():
            await asyncio.sleep(0.15)
            VL.note_verdict("other")
        task = asyncio.create_task(send())
        out = await VL.admit(onset=0.0, grace_s=0.6)
        await task
        return out
    assert _run(late()) == (False, "other_voice")


def test_the_enroll_label_carries_no_verdict_and_off_clears():
    VL.set_state(True, True)
    VL.note_verdict("enroll", now=10.0)
    assert VL.state()["pending"] == 0
    VL.note_verdict("other", now=10.0)
    VL.set_state(False, True)
    assert VL.state()["pending"] == 0, "turning the switch off forgets what was heard under it"


# ── the gate: dropped before the judge, not filed as room noise ──────────────────────────────────────────────────
def _judge(text="pon la tele más alta"):
    from voice.engine.llm.providers import attention_turn
    seen = []
    out = _run(attention_turn.judge(text, context="", emit=lambda *a, **k: seen.append((a, k))))
    return out, seen


def test_the_gate_drops_another_voice_before_the_judge(monkeypatch):
    from voice import attention
    called, ambient = [], []

    async def judge_called(*a, **k):
        called.append(a)
        return attention.Verdict(True, "always")
    monkeypatch.setattr(attention, "evaluate_content", judge_called)
    monkeypatch.setattr(attention, "note_ambient", lambda *a, **k: ambient.append(a))
    VL.set_state(True, True)
    VL.note_verdict("other")
    (directed, _text, _ms), seen = _judge()
    assert directed is False and not called, "the attention judge must not even run for another voice"
    assert not ambient, "another voice is not room noise a wake word may reclaim"
    assert any(k.get("extra", {}).get("reason") == "voice_lock" for _a, k in seen), seen
    VL.set_state(True, False)          # no enrolment: the same turn passes to the judge
    VL.note_verdict("other")
    (directed, _t, _m), _ = _judge()
    assert directed is True and called


def test_the_disarm_a_decision_that_keeps_everything_lets_the_tv_through(monkeypatch):
    monkeypatch.setattr(VL, "decide", lambda **_k: (True, "off"))
    assert VL.decide(on=True, enrolled=True, labels=["other"])[0] is True, "the mutation landed"
    VL.set_state(True, True)
    VL.note_verdict("other", now=1.0)
    assert _run(VL.admit(onset=0.9, now=2.0, grace_s=0))[0] is True   # the TV gets through: the guard is the decision


def test_the_disarm_a_gate_that_never_asks_lets_the_tv_through(monkeypatch):
    from voice import attention

    async def directed(*a, **k):
        return attention.Verdict(True, "always")
    monkeypatch.setattr(attention, "evaluate_content", directed)

    async def never(**_k):
        return True, "off"
    monkeypatch.setattr(VL, "admit", never)
    VL.set_state(True, True)
    VL.note_verdict("other")
    (d, _t, _m), _ = _judge()
    assert d is True, "with the gate disarmed another voice reaches the brain — the gate is what stops it"


# ── the wire ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_data_channel_feeds_the_lock():
    from voice.engine.pipeline import agent_events

    def pkt(topic, body):
        return SimpleNamespace(topic=topic, data=json.dumps(body).encode("utf-8"))
    kw = dict(_emit=lambda *a, **k: None, _json=json, _wake={}, session=None)
    agent_events._on_data(pkt("zaelar-voicelock", {"on": True, "enrolled": True}), **kw)
    agent_events._on_data(pkt("zaelar-speaker", {"label": "other"}), **kw)
    st = VL.state()
    assert st == {"on": True, "enrolled": True, "pending": 1}, st

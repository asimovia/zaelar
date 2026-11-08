"""The wait cover is DECIDED before the model is paid, never raced against it (V2-863, 2026-11-08).

Measured on 12 real sessions before the change: the first audio landed 2.0 s p50 after the end of turn, the cover
sounded on 8 of 25 turns, and the model was told about it CONDITIONALLY («si tu respuesta tarda, sonará X») because
the node fired it only if the first chunk lost a 1.1 s race — so the model never knew whether it had sounded, and
the operator heard both failures: the cover followed by the reply's own «dame un momento», and a reply continuing a
cover that never played. Jev's verdict (250 ms p50) could only swap the pool at the last instant.

Now `arm()` decides: the brief's sure verdict picks the pool, the style rule is applied there, a sure verdict about
a card lets a QUESTION's cover name where it looks, and the note to the model is unconditional. The node sounds the
armed phrase the moment it sees the arm — no deadline. These tests drive the REAL node wrapper with fake inner
generators, like its siblings (`test_a_tool_turn_is_covered_at_the_seam.py`).
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest
from livekit.agents.types import FlushSentinel

from nucleo.turn import brief as tb
from voice.engine.speech import filler_audio as fa


class _Brain:
    def __init__(self):
        self._last_reply = ""
        self._last_filler = ""
        self._last_spoken = ""
        self._last_spoke_at = 0.0


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.delenv("ZAELAR_FILLER_MS", raising=False)      # the default 1100 ms: the old race would wait it
    monkeypatch.setattr("voice.proactive.user_speaking", lambda: False)
    yield
    fa._reset_for_tests()


def _brief(**answers) -> dict:
    """A turn brief that has already landed: `{key: (choice, confidence)}`."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c, "confidence": conf, "probs": {}} for k, (c, conf) in
                                    answers.items()}}


def _shape(out):
    return ["FLUSH" if isinstance(c, FlushSentinel) else c for c in out]


def _inner(first_after: float, chunks=("Hace sol.",)):
    async def impl(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(first_after)
        for c in chunks:
            yield c
    return impl


def _run(impl):
    async def go():
        out, t0, flush_at = [], time.monotonic(), None
        async for c in fa.llm_node_with_filler(None, impl, None, None, None):
            if isinstance(c, FlushSentinel) and flush_at is None:
                flush_at = time.monotonic() - t0
            out.append(c)
        return out, flush_at
    return asyncio.run(go())


# ── 1. the node sounds the ARMED phrase at once, before any chunk, with no deadline ────────────────────────

def test_an_armed_cover_sounds_the_moment_the_node_sees_it_not_at_a_deadline():
    phrase = fa.arm(_Brain(), "what's on my agenda", brief=_brief(request_type=("question", 0.9)))
    assert phrase, "a question on a slow engine arms a cover"
    out, flush_at = _run(_inner(first_after=0.3))
    assert _shape(out) == [phrase + " ", "FLUSH", "Hace sol."], "the armed phrase, then the model's own words"
    assert flush_at is not None and flush_at < 0.150, f"the cover waited {flush_at:.3f}s — a deadline is back"


def test_a_fast_lane_that_answers_before_any_arm_gets_no_cover():
    """The action map, a presence knock: the model answers before the brain reaches `arm()`."""
    out, _ = _run(_inner(first_after=0.0, chunks=("Hecho.",)))
    assert _shape(out) == ["Hecho."]


# ── 2. the note to the model is UNCONDITIONAL — or absent ────────────────────────────────────────────────

def test_the_note_tells_the_model_the_cover_IS_sounding():
    messages = [{"role": "user", "content": "what's on my agenda"}]
    phrase = fa.arm(_Brain(), "what's on my agenda", messages=messages)
    note = messages[-1]["content"]
    assert phrase and f"«{phrase}»" in note
    assert "ya suena" in note, "the model is told the cover sounds, as a fact"
    assert "Si tu respuesta tarda" not in note, "the conditional wording is the race — it is gone"


def test_an_engine_answering_fast_arms_nothing_and_notes_nothing():
    for _ in range(fa._FAST_WINDOW):
        fa.note_latency(500)
    assert fa.answering_fast()
    messages = [{"role": "user", "content": "what's on my agenda"}]
    assert fa.arm(_Brain(), "what's on my agenda", messages=messages) == ""
    assert "[SISTEMA]" not in messages[-1]["content"]


# ── 3. the brief's SURE verdict decides the pool AT ARM, over the regex ─────────────────────────────────────

def test_a_sure_order_in_the_brief_picks_the_action_pool_though_the_regex_reads_a_question(monkeypatch):
    monkeypatch.setattr("nucleo.style_policy.filler_allowed", lambda k: True)
    assert fa.filler_kind("is it done?") != "action", "the regex sees a question mark, not an order"
    fa.arm(_Brain(), "is it done?", brief=_brief(request_type=("order", 0.9)))
    _, kind, _ = fa._consume_arm()
    assert kind == "action"


def test_the_style_rule_is_applied_at_arm_so_an_order_under_smart_leaves_no_note():
    """«smart» (the genesis default) drops the cover on an order. Decided at arm, the model gets no note either —
    before, the note promised a phrase that the fire site then refused to sound."""
    messages = [{"role": "user", "content": "is it done?"}]
    assert fa.arm(_Brain(), "is it done?", messages=messages, brief=_brief(request_type=("order", 0.9))) == ""
    assert fa._consume_arm() is None
    assert "[SISTEMA]" not in messages[-1]["content"]


# ── 4. a sure verdict about a CARD lets a question's cover say WHERE it looks — never an order's ──────────

@pytest.fixture
def _agenda_card(monkeypatch):
    monkeypatch.setattr("widgets.runtime.catalog", lambda: [{"id": "agenda", "name": "Agenda"},
                                                             {"id": "music", "name": "Música"}])


def test_a_question_about_a_sure_card_names_the_card(_agenda_card):
    phrase = fa.arm(_Brain(), "what's on my agenda",
                    brief=_brief(request_type=("question", 0.9), **{tb.TARGET_KEY: ("agenda::t1:show_view", 0.9)}))
    assert "Agenda" in phrase, phrase
    _, kind, armed = fa._consume_arm()
    assert (kind, armed) == ("neutral", phrase)


def test_an_unsure_card_verdict_names_nothing(_agenda_card):
    phrase = fa.arm(_Brain(), "what's on my agenda",
                    brief=_brief(request_type=("question", 0.9), **{tb.TARGET_KEY: ("agenda::t1:show_view", 0.3)}))
    assert phrase and "Agenda" not in phrase


def test_an_order_with_a_sure_card_keeps_the_motion_pool(_agenda_card, monkeypatch):
    """«Cierra la agenda» does not LOOK at the agenda: the action pool, and no card name."""
    monkeypatch.setattr("nucleo.style_policy.filler_allowed", lambda k: True)
    phrase = fa.arm(_Brain(), "close the agenda",
                    brief=_brief(request_type=("order", 0.9), **{tb.TARGET_KEY: ("agenda::t1:close", 0.9)}))
    assert phrase and "Agenda" not in phrase
    _, kind, _ = fa._consume_arm()
    assert kind == "action"

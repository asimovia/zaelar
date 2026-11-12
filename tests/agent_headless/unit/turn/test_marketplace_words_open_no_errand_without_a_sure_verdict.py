"""Marketplace words with an unsure `handle_inline` open no worker: an errand is the model's call or the brief's sure
`escalate`, never a word backstop over his sentence (CRIT-C16; group A, A3·3, 2026-11-12).

The last word-rewriter at the close: when the model called nothing, `escalation_guard.escalation_text` read his words
through `looks_like_marketplace_nav` (a site name + a search verb) and `looks_like_modify_widget` (a change verb + a
code property + «widget») and, unless the brief was SURE `handle_inline`, made the sentence an errand — a worker off a
regex, with the verdict unsure or absent. It went. What remains is the one door C16 names: the model's
`escalate_to_slowbrain`, or `route_by_verdict` on a sure `escalate_or_inline` (node 2.1618).

Seen red against the code before the removal (2026-11-12): the ES and EN turns below ended in `escalate` with the brief
at `handle_inline` 0.4 and with no brief at all — words alone opened the worker. Control: the same turn with a sure
`escalate` IS routed to its errand — the harness measures the route, not a silence.

What this does NOT cover, on purpose: the promise lane (`post_stream_lanes.run_the_light_lanes`) still asks the word
tables (`escalation_guard.word_tables` → `looks_like_escalate_task`, the window lookback) once the BRIEF says an act
was owed (`reply.owes_an_act`: a sure order or escalate) and nothing served it — CRIT-K1's documented reader, nodes
3.120 and 2.1618's neighbours. That is a verdict-gated opener, not words alone; whether it goes too is a separate step.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests import voice_turn_source as _vts

_ENGINE = Path(__file__).resolve().parents[4]

#: Site + search verb — exactly what the regex pair matched; a passing mention would not have.
TURNS = {"es": ("Búscame en Amazon un monitor de 27 pulgadas", "Claro, te busco un monitor de 27 pulgadas."),
         "en": ("Find me a 27 inch monitor on Amazon", "Sure, I'll find you a 27 inch monitor.")}


def _turn(lang: str, brief: dict):
    from tests.platform import turn_harness as H
    phrase, say = TURNS[lang]
    case = {"id": f"marketplace-words-{lang}", "lang": lang, "phrase": phrase, "source": "node 2.1728",
            "screen": {"open": []}, "model": {"say": say, "tools": []}, "expect": "talk", "brief": brief}
    try:
        out = H.run_case(case)
    finally:
        from nucleo import canvas_closes, canvas_focus, done_ops
        from nucleo.flash import bulk_close, canvas_license
        canvas_focus._reset()
        done_ops.reset()
        bulk_close.reset()
        canvas_closes._reset_for_tests()
        canvas_license._RECENT_CLOSES.clear()
    assert not out.error, out.error
    return out


@pytest.mark.parametrize("lang", ["es", "en"])
def test_marketplace_words_with_an_unsure_handle_inline_open_no_worker(lang):
    """The brief is unsure about the errand and says nothing else: his words alone used to open the worker."""
    out = _turn(lang, {"escalate_or_inline": ["handle_inline", 0.4]})
    assert "escalate" not in out.all_decisions and out.decision == "talk", out.all_decisions


@pytest.mark.parametrize("lang", ["es", "en"])
def test_marketplace_words_with_no_brief_at_all_open_no_worker(lang):
    out = _turn(lang, {})
    assert "escalate" not in out.all_decisions and out.decision == "talk", out.all_decisions


@pytest.mark.parametrize("lang", ["es", "en"])
def test_control_a_sure_escalate_verdict_routes_the_same_words_to_their_errand(lang):
    """Not a mutation: the proof that the turn above is quiet because nothing read his words, not because the harness
    cannot see an errand."""
    out = _turn(lang, {"escalate_or_inline": ["escalate", 0.95], "request_type": ["order", 0.9]})
    assert "escalate" in out.all_decisions, out.all_decisions


def test_no_word_reader_opens_an_errand_at_the_close():
    """The structural half: the readers are gone from the product, not merely unwired."""
    src = _vts.read(_ENGINE / "voice/engine/llm/providers/nucleo.py")
    for name in ("escalation_text", "looks_like_marketplace_nav", "looks_like_modify_widget", "marketplace_guard"):
        assert name not in src, f"the voice turn still reads his words through {name}"
    for rel in ("nucleo/flash/escalation_guard.py", "nucleo/flash/router_guards.py", "nucleo/flash/router.py"):
        text = (_ENGINE / rel).read_text(encoding="utf-8")
        for name in ("def escalation_text", "def looks_like_marketplace_nav", "def looks_like_modify_widget"):
            assert name not in text, f"{rel} still defines {name}"

"""Every wait of the manager has its deadline and its exit (node 13.31).

The manager is linear and deterministic with tolerance: whatever it waits for — the end of a turn, a stream, a voice
that resumed, a text behind a voice, the model, a tool, the mouth, a control, a line owed — it waits a bounded time
and then takes a declared exit; nothing is retried blindly. `WAITS` is that table, one row per wait, each with the
`Config` threshold that bounds it and the test that crosses it. A threshold of `Config` is either a wait in the table
or declared as no wait (`NOT_A_WAIT`, with its reason): a new wait cannot come in without its deadline and its test.
The waits whose crossing no other node measures are crossed here, on both sides of the deadline.
"""
from __future__ import annotations

import asyncio
import dataclasses
import importlib

import pytest

from conversation.config import Config
from conversation.ports import Done, TextDelta, ToolCall
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

U = "tests.conversation.unit."
HERE = U + "test_every_wait_has_its_deadline"

#: wait → (the thresholds that bound it, the test that crosses it — or why no test of this package can)
WAITS: dict[str, tuple[tuple[str, ...], str]] = {
    "end of turn after the voice falls": (("close_cap_ms", "patience_ms"), U + "test_one_arbiter_closes_a_turn::"
                                          "test_at_the_cap_coverage_closes_and_its_absence_is_incomplete"),
    "more patience for a declared expectation": (("patience_ms",), U + "test_one_arbiter_closes_a_turn::"
                                                 "test_a_declared_number_gives_more_patience"),
    "the provider's stream stops beating": (("stall_ms",), U + "test_one_arbiter_closes_a_turn::"
                                            "test_a_stream_that_stops_beating_ends_incomplete_with_its_words"),
    "a run stopped by a resumed voice": (("resume_window_ms", "close_cap_ms"),
                                         U + "test_the_publication_waits_for_resumed_voice::"
                                         "test_a_voice_that_never_ends_is_ended_by_the_ear_and_releases_the_batch"),
    "a text behind an open voice": (("cross_channel_hold_ms",), U + "test_voice_and_chat_share_one_order::"
                                    "test_x10_past_the_hold_cap_the_text_runs_alone_and_the_voice_comes_later"),
    "the collect window of texts": (("collect_ms",), U + "test_the_mailbox_accounts_for_every_envelope::"
                                    "test_two_texts_inside_the_collect_window_are_one_batch"),
    "the model's first event": (("model_first_ms",), U + "test_every_request_closes_once::"
                                "test_b3_a_hung_model_times_out_and_the_request_recovers_visibly"),
    "the model's next event": (("model_gap_ms",), HERE + "::test_a_model_silent_between_events_fails_the_run"),
    "a tool read": (("tool_ms",), HERE + "::test_a_slow_read_comes_back_to_the_model_as_failed"),
    "the steps of a run": (("max_steps",), HERE + "::test_a_run_past_its_steps_fails_and_the_person_is_told"),
    "a memory read": (("memory_ms",), HERE + "::test_a_slow_memory_read_leaves_the_state_without_memory"),
    "an open request": (("liveness_ms",), U + "test_every_request_closes_once::"
                        "test_b3_the_sweep_closes_the_request_of_a_run_in_course_and_stops_it"),
    "the order to the mouth": (("mouth_ms",), HERE + "::test_an_order_the_mouth_never_answers_ends_the_line_unknown"),
    "the end of a line": (("say_end_ms",), U + "test_the_mouth_knows_what_was_heard::"
                          "test_b2_a_line_nobody_acknowledges_ends_unknown_and_what_comes_next_runs"),
    "a control nobody handles": (("control_bound_ms",), U + "test_the_mailbox_accounts_for_every_envelope::"
                                 "test_a_control_whose_handler_never_ran_is_closed_by_the_sweep_with_its_reason"),
    "a line owed claimed for the voice": ((), U + "test_a_line_owed_is_said_once_by_one_channel::"
                                          "test_a_claim_past_its_deadline_goes_back"),
    "a batch held for a resumed voice, words or not": (("resume_hold_max_ms",), U + "test_the_publication_waits_"
                                                       "for_resumed_voice::test_a_continuation_longer_than_the_bound_"
                                                       "lets_the_old_batch_run_at_it"),
    "an intervention that never ends": (("intervention_max_ms",), U + "test_the_ear_holds_against_foreign_voice_"
                                        "and_background::test_a_background_with_words_and_no_end_never_holds_a_turn_open"),
    "a voice born at a close that was its tail": (("min_voice_ms",), U + "test_the_ear_holds_against_foreign_voice_"
                                                  "and_background::test_the_providers_end_before_the_fall_costs_nothing"),
    "a batch whose voice closed with no sentence mark": (("nonterminal_start_ms",), U + "test_half_a_thought_is_not_"
                                                         "answered::test_after_a_close_with_no_mark_he_goes_on_and_"
                                                         "nothing_is_said"),
    "a reply waiting for its grace": (("terminal_grace_ms", "nonterminal_grace_ms"), U + "test_half_a_thought_is_not_"
                                      "answered::test_with_nobody_going_on_the_answer_goes_at_its_grace_once"),
    "an order waiting for the grace the model read": (("complete_grace_ms", "incomplete_grace_ms"), U + "test_half_a_"
                                                      "thought_is_not_answered::test_read_as_incomplete_with_nobody_"
                                                      "going_on_it_goes_once_at_its_grace"),
    "a line cut by a voice that brought no word": (("resume_cut_within_ms",), U + "test_half_a_thought_is_not_answered"
                                                   "::test_a_line_we_stopped_or_a_breath_too_late_is_not_resumed"),
    "an open voice of an earlier epoch": ((), U + "test_a_crash_at_any_transition_recovers::"
                                          "test_a_voice_cut_by_a_restart_is_ended_incomplete_with_its_event_and_asked_again"),
}

#: waits whose bound lives outside this package or is not built yet — named so that nobody counts them done
ELSEWHERE = {
    "a voice line arriving late": "the ear's queue and the voice session live in the adapter (tramo B)",
}

#: thresholds of `Config` that bound no wait
NOT_A_WAIT = {
    "port_budget_ms": "a port slower than this is an event; the call still runs to its own deadline",
    "model_budget_ms": "the model's port: slower is an event, not a wait",
    "tools_budget_ms": "the tools' port: slower is an event, not a wait",
    "memory_budget_ms": "the memory's port: slower is an event, not a wait",
    "store_budget_ms": "a store transaction: slower is an event, not a wait",
    "mouth_budget_ms": "the mouth's port: slower is an event, not a wait",
    "evidence_ttl_ms": "how long evidence stays valid for a claim, not a wait",
    "voice_lost_window_ms": "how far back a lost voice is told with a text, not a wait",
    "session_gap_ms": "the silence that marks the turns before it as an earlier session, not a wait",
    "lost_voice_ms": "how long a voice cut with no word heard must have lasted to be his, lost and told; not a wait",
    "read_wall_ms": "the reads' time a run may spend before it must answer: a budget, each read keeps its deadline",
    "reclaim_tail_ms": "how far back a wake word takes his set-aside words back: a window, not a wait",
}


def _test(ref: str):
    mod, name = ref.split("::")
    return getattr(importlib.import_module(mod), name, None)


def test_every_wait_has_its_threshold_and_a_test_that_crosses_it():
    fields = {f.name for f in dataclasses.fields(Config)}
    for wait, (bounds, ref) in WAITS.items():
        assert set(bounds) <= fields, wait
        assert callable(_test(ref)), (wait, ref)
    assert not set(WAITS) & set(ELSEWHERE)


def test_every_threshold_of_the_manager_is_a_wait_or_says_why_not():
    thresholds = {f.name for f in dataclasses.fields(Config) if f.name.endswith("_ms") or f.name == "max_steps"}
    bounded = {b for bounds, _ref in WAITS.values() for b in bounds}
    assert thresholds - bounded == set(NOT_A_WAIT)
    assert not bounded & set(NOT_A_WAIT)


# ── the waits no other node crosses: one test each, on both sides of the deadline ─────────────────────────────────

@pytest.mark.parametrize("slow", [False, True])
def test_a_model_silent_between_events_fails_the_run(store, slow):
    h = Harness(store, grace=False, config=Config(model_gap_ms=150))
    h.model.script["iv_000001"] = [[TextDelta("w8"), asyncio.sleep(1 if slow else 0.01), reply("w9"), Done()]]
    h.utter([(["w1"], 0)])
    if not slow:
        assert [lab for lab, _ in h.closes()] == ["answered"] and [o.text for o in h.mouth.orders] == ["w9"]
        return
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "provider:timeout")]
    assert [o.notice_key for o in h.mouth.orders] == ["conv:failed:r_iv_000001"]      # the person is told, not retried


@pytest.mark.parametrize("slow", [False, True])
def test_a_slow_read_comes_back_to_the_model_as_failed(store, slow):
    h = Harness(store, grace=False, config=Config(tool_ms=150))
    h.tools.delay_s = 1.0 if slow else 0.0
    h.model.script["iv_000001"] = [[ToolCall("c1", "search", {"q": "w1"}), Done()], [reply("w9"), Done()]]
    h.utter([(["w1"], 0)])
    result = h.model.calls[-1].prompt.steps[-1][1]
    assert result.status == ("failed" if slow else "ok")
    assert [o.text for o in h.mouth.orders] == ["w9"]                          # the model decides with the failure


@pytest.mark.parametrize("over", [False, True])
def test_a_run_past_its_steps_fails_and_the_person_is_told(store, over):
    h = Harness(store, grace=False, config=Config(max_steps=3))
    tools = 3 if over else 2
    h.model.default = lambda ids: ([ToolCall(f"c{len(h.model.calls)}", "search", {"q": "w1"}), Done()]
                                   if len(h.model.calls) <= tools else [reply("w9"), Done()])
    h.utter([(["w1"], 0)])
    assert len(h.model.calls) == 3
    if not over:
        assert [lab for lab, _ in h.closes()] == ["answered"]
        return
    assert [(lab, p["reason"]) for lab, p in h.closes()] == [("recovered", "max_steps")]
    assert [o.notice_key for o in h.mouth.orders] == ["conv:failed:r_iv_000001"]


class _SlowMemory:
    def __init__(self, pause_s: float) -> None:
        self.pause_s = pause_s

    async def state_blocks(self, account, *, budget_tokens):
        await asyncio.sleep(self.pause_s)
        from conversation.ports import Block
        return [Block("memory", "w7")]


@pytest.mark.parametrize("slow", [False, True])
def test_a_slow_memory_read_leaves_the_state_without_memory(store, slow):
    h = Harness(store, grace=False, config=Config(memory_ms=150))
    h.conv.memory = _SlowMemory(1 if slow else 0.0)
    h.utter([(["w1"], 0)])
    assert [lab for lab, _ in h.closes()] == ["answered"]                     # the run goes on either way
    assert ("w7" in h.model.calls[0].prompt.state) is not slow
    assert ("conv_run/port_slow" in h.tel.labels()) is slow


class _MuteMouth:
    """A mouth that takes the order and never answers it."""

    def __init__(self, pause_s: float) -> None:
        self.pause_s, self.orders = pause_s, []

    async def say(self, order) -> None:
        self.orders.append(order)
        await asyncio.sleep(self.pause_s)


@pytest.mark.parametrize("slow", [False, True])
def test_an_order_the_mouth_never_answers_ends_the_line_unknown(store, slow):
    h = Harness(store, grace=False, config=Config(mouth_ms=150))
    h.conv.speaker.mouth = _MuteMouth(1 if slow else 0.0)
    h.utter([(["w1"], 0)])
    ended = [p["outcome"] for k, lab, p in h.tel.events if k == "conv_mouth" and lab == "ended"]
    assert [lab for lab, _ in h.closes()] == ["answered"]
    if slow:                                     # nobody waits on it: the line ended «unknown» and the manager is free
        assert ended == ["unknown"] and h.conv.state.value == "idle"
    else:                                        # answered in time, the line waits for its own acks
        assert ended == [] and h.conv.state.value == "speaking"

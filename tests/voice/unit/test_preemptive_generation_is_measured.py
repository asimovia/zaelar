"""LiveKit's preemptive generation leaves a NUMBER on our timeline: used, or thrown away (V2-863, 2026-11-08).

`preemptive_generation` has been on since the session existed here, and nothing said what it did: the SDK reuses the
early run («using preemptive generation», with its lead time) or discards it because the chat context or the tools
changed in between — one debug line each, and no metrics event. The tap turns those two lines into `perf` events.
It reads the SDK's own words, so the last test pins the two prefixes against the installed `agent_activity.py`: an
SDK that rewords them makes the tap blind, and this test red is the honest answer.
"""
from __future__ import annotations

import logging

import pytest

from voice.engine.pipeline import preemptive_tap as tap


@pytest.fixture(autouse=True)
def _clean():
    tap._reset_for_tests()
    yield
    tap._reset_for_tests()


def _install():
    seen: list = []
    handler = tap.install(lambda kind, label, text="", role="", extra=None: seen.append((kind, label, extra)))
    return handler, seen


def test_install_is_idempotent():
    h1, _ = _install()
    h2, _ = _install()
    assert h1 is h2
    lg = logging.getLogger(tap.LOGGER_NAME)
    assert sum(1 for h in lg.handlers if isinstance(h, tap._Tap)) == 1
    assert lg.isEnabledFor(logging.DEBUG), "the SDK says it at DEBUG; the logger must let it reach the tap"


def test_a_used_early_run_is_one_perf_event_with_its_lead_in_milliseconds():
    _, seen = _install()
    logging.getLogger(tap.LOGGER_NAME).debug(tap.USED_PREFIX, extra={"preemptive_lead_time": 0.42})
    assert len(seen) == 1
    kind, _label, extra = seen[0]
    assert kind == "perf" and extra["used"] is True and extra["lead_ms"] == 420


def test_a_discarded_early_run_is_one_perf_event_marked_unused():
    _, seen = _install()
    logging.getLogger(tap.LOGGER_NAME).warning(
        tap.DISCARDED_PREFIX + " after `on_user_turn_completed`")
    assert len(seen) == 1 and seen[0][0] == "perf" and seen[0][2]["used"] is False


def test_any_other_line_of_the_sdk_is_not_an_event():
    _, seen = _install()
    lg = logging.getLogger(tap.LOGGER_NAME)
    lg.debug("speech scheduled")
    lg.info("generation cancelled by user speech")
    assert seen == []


def test_the_installed_sdk_still_says_it_in_these_words():
    import livekit.agents.voice.agent_activity as aa
    src = open(aa.__file__, encoding="utf-8").read()
    assert tap.USED_PREFIX in src, "the SDK reworded the «used» line — the tap is blind to it"
    assert tap.DISCARDED_PREFIX in src, "the SDK reworded the «discarded» line — the tap is blind to it"


def test_the_model_does_not_start_on_an_unfinished_sentence_by_default():
    """V2-931 — a turn ACTS (it commissions work, answers a waiting question, sends). Started on the ear's EAGER end
    of turn it did all of that for a sentence he had not finished: measured 2026-11-17, a draft never spoken opened
    an errand and asked him about it. The model starts when the ear CONFIRMS the turn; the brief still fires early."""
    import inspect

    from voice.engine.core.config import Settings
    from voice.engine.pipeline import agent, child_session, zaelar_agent
    assert Settings.model_fields["preemptive_generation"].default is False if hasattr(Settings, "model_fields") \
        else Settings().preemptive_generation is False
    for mod in (agent, child_session):
        src = inspect.getsource(mod)
        assert '"preemptive_generation": {"enabled": SETTINGS.preemptive_generation}' in src, mod.__name__
        assert '{"enabled": True}' not in src
    assert "stt_node_firing_the_brief" in inspect.getsource(zaelar_agent), "the brief no longer fires on the eager event"

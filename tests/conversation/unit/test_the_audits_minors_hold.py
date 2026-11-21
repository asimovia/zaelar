"""The audit of B4c–B7e, its minors (node 13.89, V2-941, v3.1 B7h).

  · only HIS line at the text channel's door goes by the manager: a list's own step through `run_turn` keeps the old
    turn, switch on or not;
  · his phrase the browser's ear caught (the wake word's backstop) goes to the manager in its session as VOICE (a
    `LocalPhrase`, B10), counted apart (`wake_phrases`) — never an attempt at the old turn that would fail the proof;
  · a fixed line the operator's pack does not carry yet falls back to English, never to silence;
  · the retry pulse looks for the manager's expired claims only once the manager's host is loaded;
  · (the sandbox's reset with its two marks, closing before the queue drains, and the notices it forgets:
    `test_a_reset_leaves_nothing_of_the_cases_before`; P3 with the fixed lines and «never silence»: node 13.22).
"""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest


class _OldPath(Exception):
    pass


def test_only_his_line_at_the_door_goes_to_the_manager_with_the_switch_on(monkeypatch):
    from nucleo.cli import turn
    from nucleo.conversation_host import entry, switch
    monkeypatch.setattr(switch, "on", lambda session=None: True)
    handed = []

    async def typed_and_wait(text, dev=""):
        handed.append(text)
        return {"ok": True, "conv": {"close": "answered"}}
    monkeypatch.setattr(entry, "typed_and_wait", typed_and_wait)

    def old(sid):
        raise _OldPath(sid)
    monkeypatch.setattr(turn, "_brain", old)
    with pytest.raises(_OldPath):
        asyncio.run(turn.run_turn("w1", sid="s1", execute=True))                  # not at the door: the old turn
    assert handed == []
    assert asyncio.run(turn.run_turn("w2", sid="s1", door=True))["ok"] and handed == ["w2"]   # his line: the manager


def test_the_wake_phrase_goes_to_the_manager_counted_apart(monkeypatch):
    from nucleo.conversation_host import controls, entry, proof, switch
    from voice.engine.pipeline import agent_events
    seen = []
    monkeypatch.setattr(entry, "count", lambda c: seen.append(("count", c)))
    monkeypatch.setattr(controls, "local_phrase", lambda text, dev="": seen.append(("local_phrase", text)))
    session = SimpleNamespace(generate_reply=lambda user_input: seen.append(("old", user_input)))
    monkeypatch.setattr(switch, "on", lambda s=None: True)
    agent_events._wake_reply(session, "w1")
    assert seen == [("count", "wake_phrases"), ("local_phrase", "w1")]                    # voice, never typed
    assert "wake_phrases" in proof.COUNTERS and "wake_phrases" not in proof.MUST_BE_ZERO
    monkeypatch.setattr(switch, "on", lambda s=None: False)          # it may not answer now: nothing else does
    agent_events._wake_reply(session, "w2")
    assert seen[-1] == ("local_phrase", "w1") and ("old", "w2") not in seen


def test_a_line_the_operators_pack_lacks_falls_back_to_english(monkeypatch):
    from i18n import langs
    from nucleo.conversation_host.words import PackWords
    en = langs.spec("en")
    assert en.unverified_fact
    monkeypatch.setattr(langs, "current_language", lambda: SimpleNamespace(unverified_fact="", mute_lines=("w_own",)))
    assert PackWords().line("unverified_fact") == en.unverified_fact             # missing: English, never ""
    assert PackWords().line("mute_lines") == "w_own"                              # present: the operator's own


def test_the_retry_pulse_reads_claims_only_with_the_managers_host_loaded(monkeypatch):
    from nucleo.pulse import notice_claim, notices
    calls = []
    monkeypatch.setattr(notices._store, "claims_expired", lambda now, limit=50: calls.append(now) or [])
    monkeypatch.setattr(notices._store, "owed_due", lambda now: [])
    monkeypatch.delitem(sys.modules, "nucleo.conversation_host.owed", raising=False)
    monkeypatch.setattr(notices, "_last_retry", [0.0])
    asyncio.run(notices.retry_owed(10_000.0))
    assert calls == []                                                       # not loaded: no query on the tick
    import nucleo.conversation_host.owed  # noqa: F401 — the host loaded
    assert notice_claim.release_expired(20_000.0) == 0 and calls == [20_000]

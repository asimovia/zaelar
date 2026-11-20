"""The minors of the B7j–B8g audit hold (node 13.109, V2-941, v3.1 B7l).

  · minor 1 — a voice session nobody decided (the embedded voice) is asked the VOICE question: with the account on
    «text» it is off, so the wake phrase never goes to the manager — and «text only» is a choice, never an alert;
  · minor 3 — the account's «text» wins for the voice over a room's bare `conv=1`; a room that wants the manager's
    voice anyway says so explicitly (`conv=voice`);
  · minor 4 — a process that dies with a voice open: a SUCCESSOR born at a close that never brought a word was no
    voice, and is discarded — never «I lost that» for a loss that did not happen; one that brought words is owed;
  · minor 5 (13.100) — his voice lost: the notice is made once the ending voice no longer claims it;
  · minor 6 (13.103) — «I lost that» said in place closes `recovered`;
  · minor 7 (13.99) — our own echo, rising with our line's start, is never sent again as his voice.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.conversation_host import switch, voice_session
from tests.conversation.unit.test_a_crash_at_any_transition_recovers import Process
from conversation.testing.fakes import FakeClock, RecordingTools


@pytest.fixture
def account(monkeypatch):
    from config import settings
    from nucleo.conversation_host import config
    from voice import observer
    monkeypatch.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.delenv(switch.ENV, raising=False)
    monkeypatch.setattr(config, "build", lambda: (None, []))
    value = {"v": None, "alerts": []}
    real = settings.get
    monkeypatch.setattr(settings, "get", lambda key, default=None: value["v"] if key == switch.SETTING
                        else real(key, default))
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: value["alerts"].append(label)
                        if kind == "alert" else None)
    return value


def test_an_undecided_voice_session_asks_the_voice_question(account):
    account["v"] = "text"
    embedded = SimpleNamespace()                                           # LiveKit's own session: nobody decided it
    assert not switch.on(embedded) and switch.typed_on(embedded)          # the wake phrase stays old; text goes new
    assert account["alerts"] == []                                         # a choice, not a refusal
    assert switch.on(None)                                                 # the text door with no session: text on


@pytest.mark.parametrize("flag, voice", [("1", False), ("voice", True), ("0", False)])
def test_the_accounts_text_wins_for_the_voice_over_a_bare_room_flag(account, flag, voice):
    account["v"] = "text"
    assert voice_session.ask(flag)["on"] is voice


def test_a_room_flag_still_decides_when_the_account_is_not_text_only(account):
    account["v"] = False
    assert voice_session.ask("1")["on"] and not voice_session.ask("0")["on"]


def _died_with_a_voice_open(tmp_path, *, successor, heard):
    path, clock, tools = tmp_path / "c.db", FakeClock(t0_ms=0), RecordingTools()
    first = Process(path, clock, tools)
    first.conv.inbox.voice_open("iv_000009", 10, "d1", successor=successor)
    if heard:
        first.conv.inbox.voice_heard("iv_000009")
    first.store.close()
    second = Process(path, clock, tools)
    events = [(lab, p.get("reason")) for k, lab, p in second.tel.events if k == "conv_ear"]
    return second, events


def test_a_successor_that_never_brought_a_word_is_no_voice_lost(tmp_path):
    second, events = _died_with_a_voice_open(tmp_path, successor=True, heard=False)
    assert events == [("discarded", "restart_no_words")] and second.owed.rows == {}
    second.store.close()


@pytest.mark.parametrize("successor, heard", [(True, True), (False, False)])
def test_a_voice_that_spoke_or_rose_on_its_own_is_owed_its_line(tmp_path, successor, heard):
    second, events = _died_with_a_voice_open(tmp_path, successor=successor, heard=heard)
    assert events == [("incomplete", "restart")] and "conv:failed:r_iv_000009" in second.owed.rows
    second.store.close()


def test_the_first_word_of_a_voice_is_written_down(store):
    from conversation.ear import signals as S
    from tests.conversation.unit.convkit import Harness
    h = Harness(store)
    h.hear(S.VadEdge("d1", "rise", 10), S.WordSpan("d1", 1, 1, False, (("w1", 10, 150, 1.0),), (10, 150)))
    rows = dict(h.conv.store.view(h.conv.account).scan("voice_open", ("open",)))
    assert [r.get("heard") for r in rows.values()] == [True]

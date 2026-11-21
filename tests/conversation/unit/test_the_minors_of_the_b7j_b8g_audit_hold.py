"""The minors of the B7j–B8g audit hold (node 13.109, V2-941, v3.1 B7l).

  · (minors 1 and 3, the switch's «text only» mode, went with the unplug: the manager is the only path, INI-078 F2);
  · minor 4 — a process that dies with a voice open: a SUCCESSOR born at a close that never brought a word was no
    voice, and is discarded — never «I lost that» for a loss that did not happen; one that brought words is owed;
  · minor 5 (13.100) — his voice lost: the notice is made once the ending voice no longer claims it;
  · minor 6 (13.103) — «I lost that» said in place closes `recovered`;
  · minor 7 (13.99) — our own echo, rising with our line's start, is never sent again as his voice.
"""
from __future__ import annotations

import pytest

from tests.conversation.unit.test_a_crash_at_any_transition_recovers import Process
from conversation.testing.fakes import FakeClock, RecordingTools


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

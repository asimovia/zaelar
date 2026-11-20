"""A notice is claimed for the manager's voice, and has one consumer at a time (node 13.47, v3.1 §1.7, B6).

While a session of the manager holds the voice, `notify` CLAIMS the line — no push, no `shown`, and no paint: the
manager's mouth writes it as it says it, so it is one line (plan v3.2 C5) — so the retry and the drain to the next
screen, which read `owed`, never touch it. The manager takes each claimed line once:
said, it is `spoken`; not, it goes back to `owed` and its other ways run. A claim past its deadline goes back by
itself on the retry pulse. Claim and release compare the state: nothing moves a row that is not where it should be.
With no voice of the manager — or the manager not loaded at all — a notice runs today's path.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

from memory.api import notices as store
from nucleo.conversation_host import owed
from nucleo.pulse import notice_claim, notices


@pytest.fixture
def channels(monkeypatch):
    seen = {"painted": [], "pushed": []}

    async def paint(title, text, *, key="", speak=True, **kw):
        seen["painted"].append((text, speak))
        return True

    from voice import proactive
    monkeypatch.setattr(proactive, "notify", paint)
    monkeypatch.setattr(notices, "push", lambda row: seen["pushed"].append(row["dedupe_key"]) or 1)
    monkeypatch.setattr(notices, "_targets", lambda: ["d1"])
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: False)
    yield seen
    owed.set_voice_live(False)
    owed._handed.clear()


def _notify(key: str, text: str = "w1") -> dict:
    return asyncio.run(notices.notify("t", text, key=key))


def test_with_the_managers_voice_a_notice_is_claimed_never_painted_nor_pushed(channels):
    owed.set_voice_live(True)
    got = _notify("k1")
    assert got["state"] == "claimed" and channels["painted"] == [] and channels["pushed"] == []
    notices._last_retry[0] = 0
    asyncio.run(notices.retry_owed(now=notices._now() + 1))             # the retry reads `owed`: not this one
    assert notices.drain_to_screen() == 0                                # nor does the drain to the next screen
    assert store.by_key("k1")["state"] == "claimed" and channels["pushed"] == []


def test_the_manager_takes_each_line_once_and_its_outcome_moves_it(channels):
    owed.set_voice_live(True)
    _notify("k2", "w2")
    _notify("k3", "w3")
    port = owed.NoticesOwed()
    a, b = port.next("acct"), port.next("acct")
    assert {a.key, b.key} == {"k2", "k3"} and port.next("acct") is None   # each once
    port.settle(a.key)
    assert store.by_key(a.key)["state"] == "spoken"
    port.release(b.key)
    assert store.by_key(b.key)["state"] == "owed"                         # back to its other ways
    assert notices.drain_to_screen() == 1 and store.by_key(b.key)["state"] == "shown"


def test_claim_and_release_compare_the_state(channels):
    owed.set_voice_live(True)
    _notify("k4")
    nid = store.by_key("k4")["id"]
    assert not store.move(nid, "owed", "spoken")                         # it is not owed: nothing moves
    assert notice_claim.spoken("k4") and not notice_claim.spoken("k4") and not notice_claim.release("k4")


def test_a_claim_past_its_deadline_goes_back_on_the_retry_pulse(channels, monkeypatch):
    owed.set_voice_live(True)
    _notify("k5")
    later = notices._now() + notice_claim.CLAIM_S + 1
    monkeypatch.setattr(notices, "_now", lambda: later)
    notices._last_retry[0] = 0
    asyncio.run(notices.retry_owed(now=later))
    assert store.by_key("k5")["state"] in ("owed", "pushed")             # released, then its usual ways
    assert channels["pushed"] == ["k5"]


def test_with_no_voice_of_the_manager_it_is_todays_path(channels):
    owed.set_voice_live(False)
    assert _notify("k6")["state"] == "pushed" and channels["painted"] == [("w1", True)]


def test_with_the_manager_not_loaded_it_is_todays_path(channels, monkeypatch):
    owed.set_voice_live(True)
    monkeypatch.delitem(sys.modules, "nucleo.conversation_host.owed")
    assert _notify("k7")["state"] == "pushed"


def test_a_failed_runs_line_is_owed_under_the_key_the_manager_gave_it(channels):
    """The manager owes `conv:failed:<request>` and settles that same key once said: the port stores it as given,
    never under a second prefix the claim would never find."""
    owed.set_voice_live(True)
    owed.NoticesOwed().owe("acct", "conv:failed:r_iv_000007", "failed:provider:ReadError")
    assert store.by_key("conv:failed:r_iv_000007")["state"] == "claimed"
    assert store.by_key("conv:failed:conv:failed:r_iv_000007") is None
    line = owed.NoticesOwed().next("acct")
    assert line is not None and line.key == "conv:failed:r_iv_000007"

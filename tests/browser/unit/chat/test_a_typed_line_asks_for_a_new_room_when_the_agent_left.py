"""A typed line that finds no session asks for a new room when the agent left the one the page holds.

Measured on a phone session (2026-11-16): the agent's session closed, the page kept its room and its «live» state,
and three typed lines waited there for five minutes — `/api/chat` answered `no_session` every three seconds, the page
only started a session when it had none of its own, and the engine's timeline showed nothing of the wait. They were
delivered together after a reload.

  · the page (`services/voice-arrival.js::onNoSession`, wired in `session-lk.js`) asks for a new room when it holds one
    the agent is not in and is not still waiting for it — the node test beside this file, with its disarm;
  · the engine leaves one trace per waiting line (`screens.note_unheld`), so a wait is read, not inferred.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from voice import screens

SCRIPT = Path(__file__).with_name("test_a_typed_line_asks_for_a_new_room_when_the_agent_left.mjs")
ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _clean():
    screens._reset_for_tests()
    yield
    screens._reset_for_tests()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_asks_for_a_new_room():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_session_service_routes_no_session_through_that_decision():
    src = (ROOT / "frontend/app/services/session-lk.js").read_text(encoding="utf-8")
    assert "onNoSession: arrival.noSession(" in src
    assert "({ started, starting, watching: !!_agentWatch, agent: arrival.agentPresent(room) })" in src
    assert "() => start(), () => reconnect()" in src


def test_a_waiting_line_leaves_one_trace_and_not_one_per_retry(monkeypatch):
    seen = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: seen.append((a, k)))
    assert asyncio.run(screens.deliver_typed("add a cello lesson", "mobile:aa")) is False
    assert screens.note_unheld("add a cello lesson", "mobile:aa", now=100.0) is True
    assert screens.note_unheld("add a cello lesson", "mobile:aa", now=103.0) is False, "the page's retry is the same wait"
    assert screens.note_unheld("add a cello lesson", "mobile:aa", now=100.0 + screens.UNHELD_EVERY_S + 1) is True
    assert screens.note_unheld("another line", "mobile:aa", now=104.0) is True
    assert len(seen) == 3 and all(k.get("extra", {}).get("waiting") for _a, k in seen)


def test_the_chat_door_notes_the_wait():
    src = (ROOT / "server/screens_api.py").read_text(encoding="utf-8")
    assert "screens.note_unheld(t, dev)" in src

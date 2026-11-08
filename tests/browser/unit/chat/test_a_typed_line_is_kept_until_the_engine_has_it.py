"""A typed line is kept until the engine has it, and a waiting line is the session's first turn (operator, 2026-11-08).

Live: he typed «put some music here… an artist from "Vicios ocultos"» while the engine was stalled (the machine out of
memory). The line went down the room's data channel, which never says whether anything received it; the agent had just
dropped; the in-memory queue died with the reload; the next session greeted him «good to have you».

  · the browser's outbox (`frontend/app/services/outbox.js`) sends over HTTP and keeps the line until `ok` — node test;
  · `/api/chat` answers `no_session` until the session has STARTED (the typed door opens after `session.start`);
  · a page that holds undelivered lines says so when it asks for its room (`/api/token?pending=1`), and a line that
    arrives marks the moment — either way the session's kickoff is not a greeting (`screens.typed_waiting`).
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from voice import screens

SCRIPT = Path(__file__).with_name("test_a_typed_line_is_kept_until_the_engine_has_it.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_outbox_keeps_a_line_until_the_engine_has_it():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


@pytest.fixture(autouse=True)
def _clean():
    screens._reset_for_tests()
    yield
    screens._reset_for_tests()


def test_a_line_with_no_session_is_refused_and_nothing_waits():
    assert asyncio.run(screens.deliver_typed("hello", "desktop:aa")) is False
    assert not screens.typed_waiting()


def test_a_delivered_line_marks_that_a_typed_line_is_waiting():
    got: list = []

    async def door(text, dev):
        got.append(text)
    screens.register_typed(door)
    assert asyncio.run(screens.deliver_typed("put some music here", "desktop:aa")) is True
    assert got == ["put some music here"] and screens.typed_waiting()


def test_a_page_with_undelivered_lines_says_so_when_it_asks_for_its_room(monkeypatch):
    from server import livekit_api
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    try:
        livekit_api.token(pending=1)
    except Exception:  # noqa: BLE001 — minting the JWT needs LiveKit keys; the note is taken before it
        pass
    assert screens.typed_waiting()


def test_the_typed_door_opens_only_on_a_started_session():
    from voice.engine.pipeline import agent_events
    agent_events.open_typed_door(_emit=lambda *a, **k: None, _on_session_loop=None, session=None)
    assert not screens.has_session(), "registered before session.start: a line would reach generate_reply too early"
    src = Path("voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert src.index("await session.start(") < src.index("register_typed(_typed_from_screen)")


def test_a_waiting_line_is_checked_before_any_greeting():
    src = Path("voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert src.index("typed_waiting()") < src.index("session.generate_reply(user_input=kickoff_text")

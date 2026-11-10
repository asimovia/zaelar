"""A voice room is given only once this engine's worker is REGISTERED, and the page is ready only with the agent in it
(V2-873, node 3.185).

Measured on sandbox passes (2026-11-10): when the page asked for its room before the embedded worker had registered
with LiveKit, the room was never dispatched an agent (dispatch happens when a room is born, to the workers registered
then) — the page talked to nobody, and the boot overlay's safety timeout showed it ready anyway. Two doors:
  · `/api/token` answers 503 `voice_starting` while the embedded worker is not registered (`voice_recycle.starting`,
    the worker's LiveKit id — the same signal R21 reads), never a room nobody will join;
  · the page (`services/voice-arrival.js`, driven by `session-lk.js`) waits and asks again on that 503, leaves a room
    no agent joined within its bound, and says «ready» only with the agent in the room (the `.mjs` beside this file).
Typed lines are not routed through the token: `/api/chat` keeps its own answer while the worker registers.
Disarm: `starting()` always False — the token is minted for a worker that is not there.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nucleo.pulse import voice_recycle

_ROOT = Path(__file__).resolve().parents[3]


class _Task:
    def done(self):
        return False


def _app(worker_id: str):
    server = SimpleNamespace(id=worker_id, _closed=False, _connecting=False)
    return SimpleNamespace(state=SimpleNamespace(lk_server=server, lk_task=_Task()))


@pytest.fixture
def worker():
    before = voice_recycle._app["app"]
    yield
    voice_recycle._app["app"] = before


def test_no_room_while_the_embedded_worker_registers(worker):
    from server import livekit_api
    voice_recycle.use_app(_app("unregistered"))
    resp = livekit_api.token()
    assert resp.status_code == 503 and json.loads(resp.body) == {"error": "voice_starting"}
    voice_recycle.use_app(_app("AW_registered"))
    resp = livekit_api.token()
    assert resp.status_code == 200 and json.loads(resp.body)["token"]


def test_an_engine_without_an_embedded_worker_is_not_held(worker):
    from server import livekit_api
    voice_recycle.use_app(SimpleNamespace(state=SimpleNamespace()))
    assert livekit_api.token().status_code == 200


@pytest.mark.parametrize("text", ["hola, ¿qué hora es?", "hi, what time is it?"])
def test_a_typed_line_never_waits_on_the_token_door(worker, text):
    from server import screens_api
    voice_recycle.use_app(_app("unregistered"))
    resp = asyncio.run(screens_api.chat(text=text, dev=""))
    body = json.loads(resp.body)
    assert resp.status_code != 503 and body.get("reason") != "voice_starting", body


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_waits_for_the_agent_and_never_says_ready_without_it():
    r = subprocess.run(["node", str(Path(__file__).with_name("test_a_room_is_given_only_once_the_worker_is_registered.mjs"))],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_session_reads_the_arrival_doors():
    src = (_ROOT / "frontend/app/services/session-lk.js").read_text(encoding="utf-8")
    assert 'arrival.tokenVerdict(tk) === "starting"' in src, "a worker still registering must not take the ⏻-off path"
    assert "arrival.watchAgent(room" in src, "a room no agent joins must be left and asked for again"
    assert "unblocking anyway" not in src, "the safety timeout must never show a ready agent that is not there"
    assert "if (arrival.agentPresent(room)) { _unblockBoot(); return; }" in src

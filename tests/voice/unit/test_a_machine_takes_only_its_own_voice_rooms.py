"""An engine takes only its OWN voice rooms.

Several engines can register with one LiveKit project, and LiveKit offers a room to any worker that accepts it. With
one shared prefix an engine would accept a room another engine minted; the prefix is therefore per engine
(`FLY_MACHINE_ID` on a Fly Machine, «zaelar» elsewhere) and the match is exact.
"""
from __future__ import annotations

import pathlib

from voice.engine.core import config

_ENGINE = pathlib.Path(__file__).resolve().parents[3]


def test_each_engine_has_its_own_prefix(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("FLY_MACHINE_ID", "0a1b2c3d4e5f60")
    assert config.default_room_prefix() == "zaelar-0a1b2c3d4e5f60"
    monkeypatch.setenv("ZAELAR_USER_ID", "00000000-0000-4000-8000-000000000001")   # the agent's id wins
    assert config.default_room_prefix() == "zaelar-00000000-0000-4000-8000-000000000001"
    monkeypatch.delenv("ZAELAR_USER_ID")
    monkeypatch.delenv("FLY_MACHINE_ID")
    assert config.default_room_prefix() == "zaelar"                    # self-host: unchanged


def test_a_machine_refuses_another_machines_room():
    mine, theirs = "zaelar-0a1b2c3d4e5f60", "zaelar-9f8e7d6c5b4a30"
    assert config.accepts_room(mine, mine + "-ab12cd34")
    assert not config.accepts_room(theirs, mine + "-ab12cd34")
    assert not config.accepts_room("zaelar-0a1b", "zaelar-0a1b2c3d4e5f60-ab12cd34")   # a prefix of an id is not it


def test_the_worker_and_the_token_use_the_same_rule():
    agent = (_ENGINE / "voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert "accepts_room(SETTINGS.room_name, req.room.name)" in agent
    token = (_ENGINE / "server/livekit_api.py").read_text(encoding="utf-8")
    assert 'room = f"{SETTINGS.room_name}-' in token


def test_on_a_machine_the_session_token_names_this_engines_worker(monkeypatch):
    """Automatic dispatch offers a room to one worker at a time; a refusal elsewhere does not guarantee the owner
    is ever asked. On a Fly Machine the worker registers by name and the token names it."""
    import base64
    import json

    from server import livekit_api
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("FLY_MACHINE_ID", "0a1b2c3d4e5f60")
    assert config.dispatch_agent_name() == "zaelar-0a1b2c3d4e5f60"
    monkeypatch.setattr(livekit_api.SETTINGS.__class__, "room_name", "zaelar-0a1b2c3d4e5f60", raising=False)
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    body = json.loads(livekit_api.token().body)
    claims = json.loads(base64.urlsafe_b64decode(body["token"].split(".")[1] + "=="))
    agents = claims.get("roomConfig", {}).get("agents") or []
    assert [a.get("agentName") or a.get("agent_name") for a in agents] == ["zaelar-0a1b2c3d4e5f60"], claims
    monkeypatch.delenv("FLY_MACHINE_ID")
    assert config.dispatch_agent_name() == ""                          # self-host: automatic dispatch, unchanged


def test_the_worker_registers_under_that_name():
    agent = (_ENGINE / "voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert "agent_name=dispatch_agent_name()" in agent

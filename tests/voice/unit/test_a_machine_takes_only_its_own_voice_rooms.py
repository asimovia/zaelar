"""A cloud Machine takes only its OWN voice rooms (live, 2026-10-23).

Every cloud Machine registers its voice worker with the same LiveKit project, and every one used the prefix
«zaelar», so every Machine accepted every account's room. Measured: a new account's voice sessions were taken by
the two base Machines and by ANOTHER account's Machine — never its own — so the person spoke and nothing heard
them, and another account's engine received their audio. The prefix is now per Machine.
"""
from __future__ import annotations

import pathlib

from voice.engine.core import config

_ENGINE = pathlib.Path(__file__).resolve().parents[3]


def test_each_fly_machine_has_its_own_prefix(monkeypatch):
    monkeypatch.setenv("FLY_MACHINE_ID", "0a1b2c3d4e5f60")
    assert config.default_room_prefix() == "zaelar-0a1b2c3d4e5f60"
    monkeypatch.delenv("FLY_MACHINE_ID")
    assert config.default_room_prefix() == "zaelar"                    # self-host: unchanged


def test_a_machine_refuses_another_machines_room():
    mine, theirs = "zaelar-0a1b2c3d4e5f60", "zaelar-9f8e7d6c5b4a30"
    assert config.accepts_room(mine, mine + "-ab12cd34")
    assert not config.accepts_room(theirs, mine + "-ab12cd34")
    assert not config.accepts_room("zaelar-6835", "zaelar-0a1b2c3d4e5f60-ab12cd34")   # a prefix of an id is not it


def test_the_worker_and_the_token_use_the_same_rule():
    agent = (_ENGINE / "voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert "accepts_room(SETTINGS.room_name, req.room.name)" in agent
    token = (_ENGINE / "server/livekit_api.py").read_text(encoding="utf-8")
    assert 'room = f"{SETTINGS.room_name}-' in token

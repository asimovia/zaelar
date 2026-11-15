"""A stage of the programme is ON unless it is switched off (V2-909, `nucleo/play/switch.py`).

Every stage defaults on; a stored `false` turns one off; the env `ZAELAR_PLAY_<NAME>=0` forces it OFF over a stored
true and over the default, and no env value can force on a stage the store turned off; a name nobody declared and an
unreadable store are off.

Disarms: `stage` returns True at its head → red; `stage` ignores the env kill switch → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
STAGES = ("shadow", "own")
SRC = ROOT / "nucleo" / "play" / "switch.py"


@pytest.fixture
def cfg(monkeypatch):
    from config import v2
    store: dict = {}
    monkeypatch.setattr(v2, "_read", lambda: store)
    for n in STAGES:
        monkeypatch.delenv(f"ZAELAR_PLAY_{n.upper()}", raising=False)
    return store


def test_the_defaults_declare_every_stage_on(cfg):
    from config import v2
    from nucleo.play import switch
    assert switch.stages() == STAGES
    assert all(v is True for v in v2._DEFAULTS["play"].values())
    assert all(switch.stage(n) is True for n in STAGES)


@pytest.mark.parametrize("name", STAGES)
def test_a_stage_is_on_unless_the_store_or_the_env_switches_it_off(cfg, monkeypatch, name):
    from nucleo.play.switch import stage
    env = f"ZAELAR_PLAY_{name.upper()}"
    assert stage(name) is True                                  # the default
    cfg["play"] = {name: False}
    assert stage(name) is False                                 # a stored false turns it off
    monkeypatch.setenv(env, "1")
    assert stage(name) is False                                 # …and no env value forces it back on
    cfg["play"] = {name: True}
    monkeypatch.setenv(env, "0")
    assert stage(name) is False                                 # the env forces OFF over a stored true
    cfg.clear()
    assert stage(name) is False                                 # …and over the default


def test_an_unknown_name_and_an_unreadable_store_are_off(cfg, monkeypatch):
    from config import v2
    from nucleo.play.switch import stage
    cfg["play"] = {"own": True}
    assert stage("everything") is False

    def _broken():
        raise OSError("unreadable")
    monkeypatch.setattr(v2, "_read", _broken)
    assert stage("own") is False


def _disarmed(cfg, monkeypatch, old: str, new: str):
    from nucleo.play import switch
    orig = SRC.read_text(encoding="utf-8")
    assert old in orig, "the disarm no longer matches nucleo/play/switch.py"
    try:
        SRC.write_text(orig.replace(old, new), encoding="utf-8")
        shutil.rmtree(SRC.parent / "__pycache__", ignore_errors=True)
        assert new in SRC.read_text(encoding="utf-8")
        importlib.reload(switch)
        with pytest.raises(AssertionError):
            test_a_stage_is_on_unless_the_store_or_the_env_switches_it_off(cfg, monkeypatch, "own")
    finally:
        SRC.write_text(orig, encoding="utf-8")
        shutil.rmtree(SRC.parent / "__pycache__", ignore_errors=True)
        importlib.reload(switch)


def test_disarmed_a_stage_that_is_always_on_turns_red(cfg, monkeypatch):
    """Disarm: `stage` returns True at its head — the stored false and the env no longer turn it off."""
    head = "def stage(name: str) -> bool:\n"
    _disarmed(cfg, monkeypatch, head, head + "    return True\n")


def test_disarmed_a_stage_that_ignores_the_env_kill_switch_turns_red(cfg, monkeypatch):
    """Disarm: the env check never fires — `ZAELAR_PLAY_OWN=0` over a stored true no longer turns it off."""
    old = '    if (os.getenv(f"ZAELAR_PLAY_'
    _disarmed(cfg, monkeypatch, old, '    if False and (os.getenv(f"ZAELAR_PLAY_')

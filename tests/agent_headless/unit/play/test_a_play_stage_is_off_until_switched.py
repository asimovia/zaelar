"""A stage of the programme is OFF until it is switched on (V2-909, `nucleo/play/switch.py`).

Every stage defaults off; the config turns one on; the env can only force it OFF (`ZAELAR_PLAY_<NAME>=0`), never on;
a name nobody declared and an unreadable store are off.

Disarm: `stage` returns True → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
STAGES = ("shadow", "own")


@pytest.fixture
def cfg(monkeypatch):
    from config import v2
    store: dict = {}
    monkeypatch.setattr(v2, "_read", lambda: store)
    for n in STAGES:
        monkeypatch.delenv(f"ZAELAR_PLAY_{n.upper()}", raising=False)
    return store


def test_the_defaults_declare_every_stage_off(cfg):
    from config import v2
    from nucleo.play import switch
    assert switch.stages() == STAGES
    assert all(v is False for v in v2._DEFAULTS["play"].values())


@pytest.mark.parametrize("name", STAGES)
def test_a_stage_is_off_until_switched(cfg, monkeypatch, name):
    from nucleo.play.switch import stage
    assert stage(name) is False
    cfg["play"] = {name: True}
    assert stage(name) is True
    monkeypatch.setenv(f"ZAELAR_PLAY_{name.upper()}", "0")
    assert stage(name) is False                                 # the env forces OFF
    cfg["play"] = {name: False}
    monkeypatch.setenv(f"ZAELAR_PLAY_{name.upper()}", "1")
    assert stage(name) is False                                 # …and never forces on


def test_an_unknown_name_and_an_unreadable_store_are_off(cfg, monkeypatch):
    from config import v2
    from nucleo.play.switch import stage
    cfg["play"] = {"own": True}
    assert stage("everything") is False

    def _broken():
        raise OSError("unreadable")
    monkeypatch.setattr(v2, "_read", _broken)
    assert stage("own") is False


def test_disarmed_a_stage_that_is_always_on_turns_red(cfg, monkeypatch):
    """Disarm: `stage` returns True at its head — the off-until-switched test must fail."""
    from nucleo.play import switch
    src = ROOT / "nucleo" / "play" / "switch.py"
    orig = src.read_text(encoding="utf-8")
    head = "def stage(name: str) -> bool:\n"
    assert head in orig, "the disarm no longer matches nucleo/play/switch.py"
    try:
        src.write_text(orig.replace(head, head + "    return True\n"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert "    return True\n" in src.read_text(encoding="utf-8")
        importlib.reload(switch)
        with pytest.raises(AssertionError):
            test_a_stage_is_off_until_switched(cfg, monkeypatch, "own")
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(switch)

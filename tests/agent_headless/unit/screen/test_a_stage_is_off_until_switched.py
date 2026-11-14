"""A stage of the one screen state is OFF until it is switched on (V2-907 T2, `widgets/screen_switch.py`).

Every stage defaults off; the config turns one on; the env can only force it OFF (`ZAELAR_SCREEN_<NAME>=0`), never on;
a name nobody declared and an unreadable store are off. The config defaults declare exactly the stages the module knows.

Disarm: `stage` returns True → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def cfg(monkeypatch):
    from config import v2
    store: dict = {}
    monkeypatch.setattr(v2, "_read", lambda: store)
    for n in ("READ", "CONFIRM", "DIRECT"):
        monkeypatch.delenv(f"ZAELAR_SCREEN_{n}", raising=False)
    return store


def test_the_defaults_declare_every_stage_off(cfg):
    from config import v2
    from widgets import screen_switch
    assert screen_switch.stages() == ("read", "confirm", "direct")
    assert all(v is False for v in v2._DEFAULTS["screen"].values())


@pytest.mark.parametrize("name", ["read", "confirm", "direct"])
def test_a_stage_is_off_until_switched(cfg, monkeypatch, name):
    from widgets.screen_switch import stage
    assert stage(name) is False
    cfg["screen"] = {name: True}
    assert stage(name) is True
    monkeypatch.setenv(f"ZAELAR_SCREEN_{name.upper()}", "0")
    assert stage(name) is False                                 # the env forces OFF
    cfg["screen"] = {name: False}
    monkeypatch.setenv(f"ZAELAR_SCREEN_{name.upper()}", "1")
    assert stage(name) is False                                 # …and never forces on


def test_an_unknown_name_and_an_unreadable_store_are_off(cfg, monkeypatch):
    from config import v2
    from widgets.screen_switch import stage
    cfg["screen"] = {"read": True}
    assert stage("everything") is False

    def _broken():
        raise OSError("unreadable")
    monkeypatch.setattr(v2, "_read", _broken)
    assert stage("read") is False


def test_disarmed_a_stage_that_is_always_on_turns_red(cfg, monkeypatch):
    """Disarm: `stage` returns True at its head — the off-until-switched test must fail."""
    from widgets import screen_switch
    src = ROOT / "widgets" / "screen_switch.py"
    orig = src.read_text(encoding="utf-8")
    head = "def stage(name: str) -> bool:\n"
    assert head in orig, "the disarm no longer matches screen_switch.py"
    try:
        src.write_text(orig.replace(head, head + "    return True\n"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert "    return True\n" in src.read_text(encoding="utf-8")
        importlib.reload(screen_switch)
        with pytest.raises(AssertionError):
            test_a_stage_is_off_until_switched(cfg, monkeypatch, "read")
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(screen_switch)

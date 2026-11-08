"""The picture viewer declares the REAL end state of each act (four principles, P2).

`show` used to be done when `items` was present — and the OLD set still held satisfied it, so a show that put nothing
new on screen read as delivered. Each set put on screen bumps `set_seq` (a value in the view, never absent), and
`show` is done when it changed; `local`, `slideshow` and `select` declare the field their act moves (`add` declares
none: an add that finds nothing new is not a failure).
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from nucleo.circuit import baseline, verify
from widgets import store
from widgets.imagenes import data as im

_MANIFEST = json.load(open(im.__file__.replace("data.py", "manifest.json"), encoding="utf-8"))
_OLD = [{"url": "https://e.x/a.jpg", "title": "Crab nebula"}, {"url": "https://e.x/b.jpg", "title": "Orion"}]
_NEW = [{"url": "https://e.x/c.jpg", "title": "Ferrari F40"}, {"url": "https://e.x/d.jpg", "title": "F40 red"}]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))


def _dw(action: str):
    dw = copy.deepcopy(_MANIFEST["actions"][action]["done_when"])
    baseline.snapshot(dw)
    return dw


def test_set_seq_is_a_value_in_the_view_even_on_an_old_store():
    store.save("imagenes", {"items": _OLD})            # written before the counter existed
    assert im.view_data()["set_seq"] == 0


def test_the_old_set_still_held_does_not_meet_a_show():
    im.apply_action("show", {"items": _OLD, "query": "nebula"})
    dw = _dw("show")
    assert verify.check(dw) is False, "the old set on screen is not the new show"
    assert im.apply_action("show", {"items": [], "query": "ferrari f40"})["ok"] is False
    assert verify.check(dw) is False, "a refused empty show put nothing new on screen"
    assert im.apply_action("show", {"items": _NEW, "query": "ferrari f40"})["ok"]
    assert verify.check(dw) is True


def test_a_held_set_that_answers_the_show_is_the_show():
    im.apply_action("show", {"items": _OLD, "query": "crab nebula"})
    dw = _dw("show")
    got = im.apply_action("show", {"items": [], "query": "crab nebula"})
    assert got.get("already_shown")
    assert verify.check(dw) is True


def test_local_is_done_when_the_local_set_is_on_screen():
    im.apply_action("show", {"items": _OLD, "query": "nebula", "source": "google"})
    dw = _dw("local")
    assert verify.check(dw) is False
    open(os.path.join(store.data_dir("imagenes"), "beach.jpg"), "wb").write(b"\xff\xd8")
    assert im.apply_action("local", {})["ok"]
    assert verify.check(dw) is True


@pytest.mark.parametrize("action,payload", [
    ("slideshow", {}), ("select", {"item": "2"})])
def test_each_act_is_done_when_its_field_moved(action, payload):
    im.apply_action("show", {"items": _OLD, "query": "nebula"})
    dw = _dw(action)
    assert verify.check(dw) is False, "before the act"
    assert im.apply_action(action, payload)["ok"]
    assert verify.check(dw) is True

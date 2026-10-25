"""Every widget, on two screens at once (V2-792, node 4.270).

The catalogue decides the cases, not a list in this file: every widget with a card is opened from the computer and
then from the phone, in two real browsers on one engine, and must do what its own manifest says (`"screens"`) —
a `shared` reflection stays open on both, a `single` card that takes the device's sound or picture moves to the phone
and leaves the computer. A widget added tomorrow is in this test the moment it is in the catalogue. The harness is
`two_screens.py` beside this file; the operator's manual pass with a real phone is
`.meshkore/docs/ops/zaelar-two-screen-test.md`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from two_screens import TwoScreens  # noqa: E402


def _catalogue() -> list[str]:
    from widgets import runtime
    return sorted(str(w["id"]) for w in runtime.catalog() if w.get("id") and not w.get("transient"))


@pytest.fixture(scope="module")
def screens():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    with TwoScreens() as ts:
        yield ts


def test_the_catalogue_is_not_empty():
    assert len(_catalogue()) >= 10


@pytest.mark.parametrize("wid", _catalogue())
def test_the_widget_does_what_its_screens_policy_says(screens, wid):
    failed = [what for ok, what in screens.check(wid) if not ok]
    assert not failed, f"{wid} ({screens.policy(wid)}): {failed}"


def test_no_page_error_on_either_screen(screens):
    assert not screens.errors, screens.errors

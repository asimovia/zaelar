"""The timer on a phone, RENDERED at 393×852 inside the deck's card (V2-876 P-33, V2-877 #12).

What a phone showed: the timer's digits in a monospace face with a slashed zero, a dangling «· · ·» under them,
no control at all with nothing set although the card promises pause / resume / reset, and a frame of its own.
And the timer's manifest declared no actions at all, so `set` — the one thing a voice asks of it — was not part of its data API.

Disarm: put `ui-monospace` back on `.ht-digits` → red.
"""
from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.phone_apps._phone import phone  # noqa: E402

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_the_timer_declares_the_actions_its_data_layer_runs():
    m = json.loads((_ENGINE / "widgets/timer/manifest.json").read_text())
    assert set(m.get("actions") or {}) == {"set", "start", "pause", "reset"}, m.get("actions")
    from widgets.timer import data
    for a in ("start", "pause", "reset"):
        assert data.apply_action(a, {}).get("ok"), a
    assert data.apply_action("set", {"seconds": 5}).get("ok")
    data.apply_action("reset", {})


@pytest.fixture(scope="module")
def timer():
    with phone("timer") as pg:
        yield pg


def _timer(pg, data):
    pg.evaluate("() => { try{ localStorage.clear(); }catch(_){} }")
    pg.evaluate("(d) => window.__render(d)", data)
    return pg.evaluate("""() => { const d = document.querySelector('.ht-digits'), cs = getComputedStyle(d);
        const btns = [...document.querySelectorAll('.hb-timer button')];
        return {fs: parseFloat(cs.fontSize), fam: cs.fontFamily, text: document.querySelector('.hb-timer').innerText,
                buttons: btns.map(b => b.textContent), minH: Math.min(...btns.map(b => b.getBoundingClientRect().height))}; }""")


def test_the_empty_timer_offers_its_own_starts_and_no_dots(timer):
    m = _timer(timer, {"remaining": 0, "running": False, "finished": False, "target_seconds": 0})
    assert m["fs"] >= 40 and "mono" not in m["fam"].lower(), m
    assert "· · ·" not in m["text"], m["text"]
    assert len(m["buttons"]) == 3 and m["minH"] >= 44, m
    timer.evaluate("() => document.querySelector('.hb-timer button[data-min=\"5\"]').click()")
    timer.wait_for_timeout(100)
    assert ["set", {"seconds": 300}] in timer.evaluate("() => window.__acts")
    after = timer.evaluate("() => [...document.querySelectorAll('.hb-timer button')].map(b => b.textContent)")
    assert any("Pause" in b or "pause" in b for b in after), f"a started countdown shows its pause: {after}"


def test_a_running_timer_has_pause_and_cancel_at_44pt(timer):
    m = _timer(timer, {"remaining": 540, "running": True, "finished": False, "target_seconds": 600, "label": "pasta"})
    assert m["fs"] >= 40 and len(m["buttons"]) == 2 and m["minH"] >= 44, m

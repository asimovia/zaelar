"""The clock on a phone, RENDERED at 393×852 inside the deck's card (V2-876 P-33, V2-877 #12).

What a phone showed: a framed box over a quarter of the page, monospace figures, the zone as a raw IANA id. The zone
is the SCREEN's own (the device he holds) — the engine has no time-zone setting for the person; a `tz` the engine
sends wins.

Disarm: give `.hb-clock` its fixed frame back (`border:1px solid`) → red.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.phone_apps._phone import phone  # noqa: E402


def test_the_clock_fills_its_page_and_names_its_zone():
    with phone("clock") as pg:
        pg.evaluate("(d) => window.__render(d)", {})
        m = pg.evaluate("""() => { const c = document.querySelector('.hb-clock'), sc = document.querySelector('.zm-scroll');
            const t = document.querySelector('.hb-clock .time');
            return {h: c.getBoundingClientRect().height, sh: sc.clientHeight, border: getComputedStyle(c).borderTopWidth,
                    fam: getComputedStyle(t).fontFamily, fs: parseFloat(getComputedStyle(t).fontSize),
                    tz: document.querySelector('.hb-clock .tz').textContent}; }""")
        assert m["h"] >= 0.9 * m["sh"], f"the clock fills its page: {m}"
        assert m["border"] in ("0px", ""), "no frame of its own — the chrome is the host's"
        assert m["fs"] >= 40 and "mono" not in m["fam"].lower(), m
        assert m["tz"] and "/" not in m["tz"], f"the zone by its name, not its IANA id: {m['tz']!r}"
        pg.evaluate("(d) => window.__render(d)", {"tz": "America/Los_Angeles"})
        tz = pg.evaluate("() => document.querySelector('.hb-clock .tz').textContent")
        assert "Pacific" in tz, f"a zone the engine knows for him wins over the device's: {tz!r}"

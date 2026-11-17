"""The phone shell shows the build number at the foot of its ☰ page, live (2026-11-17, node 4.568).

The operator: the build number visible on the phone too, subtle, at the bottom of the menu that opens from the dock,
under the energy and account rows. It is the desktop badge's own element (`update/VersionLabel.js`) reading the same
`update/watch.js` signals, so the number follows `GET /api/update` without a reload; and the phone mounts the update
surface WITHOUT the desktop's floating badge — one number per shell.

RENDERED: the real surfaces from `shell/mobile-surfaces.js` and the real stylesheets, in Chromium at 393×852 with touch.
"""
from __future__ import annotations

import json

import pytest

from tests.browser.unit.mobile.phone_page import open_phone, shot

_PAYLOAD = {"build": 150, "version": "3.45", "sha": "abc1234", "short": "b150+abc1234", "ui_rev": "r1",
            "started_ms": 0, "deploy": "local"}
_SERVED = {"payload": dict(_PAYLOAD)}


def _update(route):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(_SERVED["payload"]))


SETUP = """
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  for (const id of ['menu', 'update']) document.body.append(MOBILE_SURFACES.find(s => s.id === id).comp());
  window.__store.setCloudProfile(true);
  window.__store.setEnergy({ cloud: true, known: true, balance: 61, capacity: 400 });
  window.__store.setMobileMenuOpen(true);
"""

_STATE = """() => {
  const page = document.querySelector('.zm-page[data-page="menu"]');
  const ver = page && page.querySelector('.hb-ver');
  const body = page && page.querySelector('.zm-page-b');
  if (body) body.scrollTop = body.scrollHeight;
  const r = ver ? ver.getBoundingClientRect() : null;
  const rows = page ? [...page.querySelectorAll('.zm-row, .zm-energy')].filter(e => e.getBoundingClientRect().height > 0) : [];
  const last = rows.length ? rows[rows.length - 1].getBoundingClientRect() : null;
  const cs = ver ? getComputedStyle(ver) : null;
  return {
    found: !!ver, text: ver ? ver.textContent.trim() : '',
    visible: !!(r && r.width > 0 && r.height > 0 && cs.display !== 'none'),
    belowRows: !!(r && last && r.top >= last.bottom - 1),
    fontPx: cs ? parseFloat(cs.fontSize) : null, opacity: cs ? parseFloat(cs.opacity) : null,
    floatingBadge: !!document.getElementById('hb-upd-ver'),
  };
}"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP, routes=[("**/api/update", _update)]) as pg:
        pg.wait_for_timeout(500)
        yield pg


def test_the_menu_ends_with_the_build_number_quiet_and_live(phone):
    s = phone.evaluate(_STATE)
    assert s["found"], "the ☰ page has no build number"
    assert s["visible"] and s["text"] == "v150", f"the ☰ page shows {s['text']!r}, the engine says v150: {s}"
    assert s["belowRows"], f"the build number must sit at the foot of the page, under every row: {s}"
    assert s["fontPx"] <= 12 and s["opacity"] < 1, f"the build number has to be subtle: {s}"
    assert not s["floatingBadge"], "the phone mounted the desktop's floating badge as well — one number per shell"
    shot(phone, "menu-build-number")

    # a tap shows build + commit, for a phone that has no hover tooltip
    phone.click('.zm-page[data-page="menu"] .hb-ver')
    phone.wait_for_timeout(300)
    assert phone.evaluate(_STATE)["text"] == "v150 · b150+abc1234"

    # live: the engine reports a new build, the number follows without a reload
    _SERVED["payload"] = {**_PAYLOAD, "build": 151, "short": "b151+def5678"}
    phone.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    phone.wait_for_timeout(500)
    assert phone.evaluate(_STATE)["text"].startswith("v151"), "the ☰ page did not follow the engine live"
    assert not phone._errors, phone._errors

"""⏻ is one door; the microphone and the deck are others (V2-877 #4, #11; V2-654).

Seen on the review account (2026-11-11): switching the agent on opened a microphone he had closed, and closed the
eight cards his hand had opened. The mic: a stop remembers the mic it found and ⏻ on puts THAT back. The deck: the
reconnect that ⏻ on causes re-reports the phone's cards instead of adopting `/api/canvas/layout` (the desktop's
geometry — empty for an account with no desktop), so nothing the hand opened closes.

RENDERED: the real `services/power.js` + `services/mic.js` and the real `Deck`, at 393×852 with touch.
"""
from __future__ import annotations

import json

import pytest

from tests.browser.unit.mobile.phone_page import open_phone, shot

_CLOCK_JS = "export function render(el) { el.innerHTML = '<p class=\"stub\">' + Math.random() + '</p>'; }"


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript", body=_CLOCK_JS)
    if path in ("", "/"):
        body = {"widgets": [{"id": w} for w in ("clock", "agenda", "musica")]}
    elif path == "/registry":
        body = {"registry": [{"id": w, "name": w.title(), "surface": "user", "origin": "builtin"}
                             for w in ("clock", "agenda", "musica")]}
    else:
        body = {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


SETUP = """
  window.__power = await import('/frontend/app/services/power.js?v=1');
  window.__mic = await import('/frontend/app/services/mic.js?v=1');
  const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(stage);
"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP, routes=[(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets),
                                   ("**/api/canvas/layout*", lambda r: r.fulfill(
                                       status=200, content_type="application/json",
                                       body=json.dumps({"items": [], "live": [], "elsewhere": []})))]) as pg:
        yield pg


def _cycle(pg, before_off: bool, while_off=None) -> bool:
    """Set the mic, press ⏻ off, optionally touch the mic while stopped, press ⏻ on → the mic after."""
    return pg.evaluate("""async ([muted, during]) => {
        localStorage.removeItem('hb_mic_before_power');
        window.__mic.setMuted(muted, 'dock');
        window.__power.setPower(true, 'dock');
        if (window.__store.micMuted() !== true) return 'stop did not close the mic';
        if (during !== null) window.__mic.setMuted(during, 'dock');
        window.__power.setPower(false, 'dock');
        return window.__store.micMuted(); }""", [before_off, while_off])


def test_power_on_never_opens_a_mic_he_had_closed(phone):
    assert _cycle(phone, True) is True


def test_power_on_gives_back_an_open_mic(phone):
    assert _cycle(phone, False) is False


def test_a_mic_closed_by_hand_while_stopped_stays_closed(phone):
    assert _cycle(phone, False, while_off=True) is True


def test_a_stop_from_another_screen_counts_as_a_stop(phone):
    got = phone.evaluate("""() => {
        localStorage.removeItem('hb_mic_before_power');
        window.__mic.setMuted(true, 'dock');
        window.__mic.setMuted(true, 'server-stopped');
        window.__power.setPower(false, 'dock');
        return window.__store.micMuted(); }""")
    assert got is True


def test_power_on_keeps_every_card_the_hand_opened(phone):
    phone.evaluate("""async () => {
        for (const id of ['clock', 'agenda', 'musica']) await window.__deck.show(id, { by: 'hand' });
        window.__power.setPower(true, 'dock');
        window.__power.setPower(false, 'dock');
        await window.__deck.reconcile();          // what the stream's reopen after ⏻ on runs (services/sse.js)
    }""")
    phone.wait_for_timeout(400)
    assert phone.evaluate("() => window.__deck.list()") == ["clock", "agenda", "musica"]
    assert phone.evaluate("() => document.querySelectorAll('.zm-card[data-wid]').length") == 3
    reports = [p["body"] for p in phone._posts if p["url"] == "/api/canvas/state"]
    assert reports and reports[-1]["open"] == ["clock", "agenda", "musica"], \
        "the reconnect re-reports the deck, so the engine learns what the hand opened"
    shot(phone, "pr1-power-on-keeps-cards")


def test_an_orphan_card_the_deck_does_not_own_still_goes(phone):
    phone.evaluate("""async () => { const c = document.createElement('div'); c.className = 'zm-card';
        c.dataset.wid = 'ghost'; window.__deck.stage.append(c); await window.__deck.reconcile(); }""")
    assert phone.evaluate("() => !!document.querySelector('.zm-card[data-wid=\"ghost\"]')") is False


def test_no_script_error(phone):
    assert not phone._errors, phone._errors

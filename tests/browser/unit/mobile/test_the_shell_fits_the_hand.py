"""The phone shell fits the hand (V2-876 P-10, P-11/P-12, P-13, P-15, P-17, P-19), one test per rule.

· paging: a sideways swipe moves ONE page; a vertical scroll never pages; the pips row is the switcher — a tap goes
  there, a finger dragged along it goes through the pages under it; more than five apps collapse to five pips and a
  «k/n» counter; the row is its own band, never inside a card's frame;
· the orb: its whole box inside the screen and the dock (never clipped), and ONE mic indicator — the mic button;
· Home: a greeting, his next three appointments in order, what is playing, and the «Talk to zaelar» hint below;
· the chat: 44pt composer, the newest line in sight with the keyboard up, answers wrapped at 32em in 16px text;
· the dock: 44pt targets 8pt apart, and a long press says a control's name without toggling it.

RENDERED: the real Deck, dock and chat page with the real stylesheets, in Chromium at 393×852 with touch, in Spanish.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from tests.browser.unit.mobile.phone_page import PACK, H, W, open_phone, shot

ES = PACK["es"]
APPS = ["agenda", "clock", "contactos", "documento", "fotos", "imagenes", "map"]
_STUB = ("export function render(el) { el.innerHTML = '<div style=\"height:2400px\" class=\"stub\">' "
         "+ 'línea '.repeat(400) + '</div>'; }")
_NOW = dt.datetime.now()


def _meetings():
    day = lambda d: (_NOW + dt.timedelta(days=d)).strftime("%Y-%m-%d")
    return [{"date": day(-1), "startTime": "09:00", "title": "Ayer"},
            {"date": day(3), "startTime": "10:00", "title": "Dentista"},
            {"date": day(1), "startTime": "08:30", "title": "Café con Ana"},
            {"date": day(2), "startTime": "18:00", "title": "Pádel"},
            {"date": day(5), "startTime": "12:00", "title": "Comida"}]


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript", body=_STUB)
    if path == "/agenda/data":
        body = {"meetings": _meetings()}
    elif path == "/musica/data":
        body = {"now_playing": {"playing": True, "title": "Despechá", "artist": "Rosalía"}}
    elif path == "/musica/manifest":
        body = {"runtime": {"active_when": [{"now_playing.playing": True}]}}
    elif path in ("", "/"):
        body = {"widgets": [{"id": a} for a in APPS + ["musica"]]}
    else:
        body = {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


SETUP = """
  const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(stage);
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  for (const id of ['dock', 'chat']) document.body.append(MOBILE_SURFACES.find(s => s.id === id).comp());
  window.__mic = await import('/frontend/app/services/mic.js?v=1');
  window.__store.setPowerOff(false);
"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP, routes=[(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets)]) as pg:
        pg.wait_for_timeout(300)
        yield pg


SWIPE = """async ([x0, y0, x1, y1]) => {
  const target = document.elementFromPoint(x0, y0);
  const mk = (x, y) => new Touch({ identifier: 1, target, clientX: x, clientY: y });
  const fire = (type, x, y) => target.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true,
      touches: type === 'touchend' ? [] : [mk(x, y)], changedTouches: [mk(x, y)] }));
  fire('touchstart', x0, y0);
  for (let i = 1; i <= 12; i++) fire('touchmove', x0 + (x1 - x0) * i / 12, y0 + (y1 - y0) * i / 12);
  fire('touchend', x1, y1);
  await new Promise(r => setTimeout(r, 120));
  return window.__deck.at; }"""


def _open(pg, ids):
    pg.evaluate("async (ids) => { for (const id of ids) await window.__deck.show(id, { by: 'hand' }); }", ids)
    pg.wait_for_timeout(200)


def test_a_swipe_moves_one_page_and_a_scroll_never_pages(phone):
    _open(phone, ["clock", "agenda", "contactos"])
    phone.evaluate("() => window.__deck._goTo(1, 0)")
    assert phone.evaluate(SWIPE, [300, 400, 40, 410]) == 2, "a long sideways swipe moves ONE page, not two"
    assert phone.evaluate(SWIPE, [60, 400, 330, 395]) == 1
    assert phone.evaluate(SWIPE, [200, 600, 230, 150]) == 1, "a vertical scroll (with some drift) never pages"
    assert phone.evaluate(SWIPE, [200, 300, 190, 700]) == 1


def test_the_pips_are_a_switcher_by_tap_and_by_drag(phone):
    phone.evaluate("() => window.__deck._goTo(0, 0)")
    phone.tap(".zm-pips .zm-pip[data-k='2']")
    phone.wait_for_timeout(100)
    assert phone.evaluate("() => window.__deck.at") == 2
    b = phone.evaluate("""() => [...document.querySelectorAll('.zm-pips .zm-pip')].map(p => {
        const r = p.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })""")
    (hx, hy), (lx, ly) = b[0], b[-1]
    at = phone.evaluate(SWIPE, [lx, ly, hx, hy])
    assert at == -1, "dragging along the row goes through the pages under the finger, to the home"


def test_beyond_five_apps_the_row_collapses_with_a_counter_and_sits_outside_every_card(phone):
    _open(phone, APPS)
    phone.evaluate("() => window.__deck._goTo(5, 0)")
    phone.wait_for_timeout(300)
    g = phone.evaluate("""() => { const row = document.querySelector('.zm-pips');
        const card = document.querySelector('.zm-card.live').getBoundingClientRect();
        const r = row.getBoundingClientRect(), dock = document.querySelector('.zm-dock').getBoundingClientRect();
        return {pips: row.querySelectorAll('.zm-pip').length, n: window.__deck.order.length,
                counter: (row.querySelector('.zm-pipn') || {}).textContent || '',
                cardBottom: card.bottom, rowTop: r.top, rowBottom: r.bottom, dockTop: dock.top,
                lit: !!row.querySelector('.zm-pip.on[data-k="5"]')}; }""")
    assert g["n"] == 7 and g["pips"] == 6, f"home + five, never a row of seven dots: {g}"
    assert g["counter"] == "6/7" and g["lit"], g
    assert g["cardBottom"] <= g["rowTop"] + 0.5 and abs(g["rowBottom"] - g["dockTop"]) <= 1, \
        f"the pips are their own band between the card and the dock: {g}"
    shot(phone, "pr3-pips-collapsed")
    phone.evaluate("() => window.__deck.closeAll({ by: 'hand' })")
    phone.wait_for_timeout(300)


def test_the_orb_is_never_clipped_and_the_mic_button_is_the_one_mic_indicator(phone):
    phone.evaluate("() => window.__mic.setMuted(true, 'dock')")
    phone.wait_for_timeout(100)
    g = phone.evaluate("""() => { const o = document.querySelector('.zm-orb-btn').getBoundingClientRect();
        const d = document.querySelector('.zm-dock').getBoundingClientRect();
        const glyph = document.querySelector('.zm-orb-mic');
        return {top: o.top, bottom: o.bottom, dockTop: d.top, H: innerHeight,
                orbMic: getComputedStyle(glyph).display,
                micBtn: document.querySelector('.zm-dock [data-ctl="mic"]').getAttribute('aria-label')}; }""")
    phone.evaluate("() => window.__mic.setMuted(false, 'dock')")
    assert g["bottom"] <= g["H"] and g["top"] >= g["dockTop"] - 10, f"the orb stays inside the screen and the bar: {g}"
    assert g["orbMic"] == "none", "the orb does not repeat the mic's state"
    assert g["micBtn"] == ES["camera.mic_unmute"], g


def test_home_shows_today_with_the_hint_below(phone):
    _open(phone, ["musica"])
    phone.evaluate("() => window.__deck.home()")
    phone.wait_for_function("() => document.querySelectorAll('.zm-today .zm-today-row.appt').length === 3", timeout=5000)
    phone.wait_for_function("() => !!document.querySelector('.zm-today .zm-today-row.play')", timeout=5000)
    g = phone.evaluate("""() => ({
        greet: document.querySelector('.zm-today h2').textContent,
        appts: [...document.querySelectorAll('.zm-today-row.appt span')].map(s => s.textContent),
        play: document.querySelector('.zm-today-row.play span').textContent,
        rows: [...document.querySelectorAll('.zm-today-row')].map(r => r.getBoundingClientRect().height)})""")
    greetings = {ES[k] for k in ("mobile.greet_morning", "mobile.greet_afternoon", "mobile.greet_night")}
    assert g["greet"] in greetings, g
    assert g["appts"] == ["Café con Ana", "Pádel", "Dentista"], "the next three, in order, nothing past"
    assert g["play"] == "Despechá · Rosalía"
    assert min(g["rows"]) >= 44
    shot(phone, "pr3-home-today")
    phone.evaluate("() => window.__deck.closeAll({ by: 'hand' })")
    phone.wait_for_timeout(300)
    g = phone.evaluate("""() => ({today: document.querySelector('.zm-today').getBoundingClientRect().bottom,
        hint: document.querySelector('.zm-empty.on h2').getBoundingClientRect().top})""")
    assert g["hint"] >= g["today"], f"the hint sits below today: {g}"
    shot(phone, "pr3-home-empty")


def test_the_chat_composer_is_44pt_and_the_newest_line_stays_in_sight_over_the_keyboard(phone):
    phone.evaluate("""async () => { const k = await import('/frontend/mobile/app/shell/keyboard.js?v=2'); k.initKeyboard();
        window.__store.setChatMsgs([]); for (let i = 0; i < 30; i++) window.__store.pushAgentChat('Respuesta ' + i + ' ' + 'palabra '.repeat(40));
        window.__store.setChatOpen(true); }""")
    phone.wait_for_timeout(300)
    sz = phone.evaluate("""() => ['.zm-compose input', '.zm-send'].map(s => {
        const r = document.querySelector('.zm-page[data-page="chat"] ' + s).getBoundingClientRect(); return [r.width, r.height]; })""")
    assert all(h >= 44 for _, h in sz) and sz[1][0] >= 44, sz
    font = phone.evaluate("() => getComputedStyle(document.querySelector('.zm-msg.agent')).fontSize")
    assert font == "16px", font
    phone.focus(".zm-page[data-page='chat'] .zm-compose input")
    phone.set_viewport_size({"width": W, "height": H - 336})
    phone.wait_for_timeout(400)
    g = phone.evaluate("""() => { const p = document.querySelector('.zm-page[data-page="chat"]');
        const last = [...p.querySelectorAll('.zm-msg')].pop().getBoundingClientRect();
        const comp = p.querySelector('.zm-compose').getBoundingClientRect();
        const list = p.querySelector('.zm-msgs').getBoundingClientRect();
        return {lastBottom: last.bottom, lastTop: last.top, compTop: comp.top, listTop: list.top, vh: innerHeight}; }""")
    shot(phone, "pr3-chat-keyboard")
    phone.evaluate("() => { document.activeElement.blur(); window.__store.setChatOpen(false); }")
    phone.set_viewport_size({"width": W, "height": H})
    phone.wait_for_timeout(200)
    assert g["lastBottom"] <= g["compTop"] + 1 and g["lastBottom"] > g["listTop"], \
        f"with the keyboard up the newest line is in sight above the composer: {g}"


def test_the_dock_is_44pt_targets_8pt_apart_and_a_long_press_says_the_name(phone):
    g = phone.evaluate("""() => [...document.querySelectorAll('.zm-dock .zm-side')].map(s =>
        [...s.querySelectorAll('button')].map(b => { const r = b.getBoundingClientRect(); return [r.left, r.right, r.height]; }))""")
    for side in g:
        assert all(r - l >= 44 and h >= 44 for l, r, h in side), g
        assert all(side[i + 1][0] - side[i][1] >= 8 for i in range(len(side) - 1)), f"8pt apart: {g}"
    chat_open = "() => window.__store.chatOpen()"
    before = phone.evaluate(chat_open)
    box = phone.evaluate("""() => { const b = document.querySelector('.zm-dock .zm-side button:nth-child(2)');
        const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2, b.getAttribute('aria-label')]; }""")
    phone.mouse.move(box[0], box[1])
    phone.mouse.down()
    phone.wait_for_timeout(650)
    tip = phone.evaluate("() => { const t = document.querySelector('.zm-tip'); return [t.classList.contains('show'), t.textContent]; }")
    shot(phone, "pr3-dock-long-press")
    phone.mouse.up()
    phone.wait_for_timeout(100)
    assert tip == [True, box[2]], tip
    assert phone.evaluate(chat_open) == before, "the long press said the name and did not toggle the chat"
    phone.tap(".zm-dock .zm-side button:nth-child(2)")
    phone.wait_for_timeout(100)
    assert phone.evaluate(chat_open) != before, "a plain tap still works"
    phone.evaluate("() => window.__store.setChatOpen(false)")


def test_no_script_error(phone):
    assert not phone._errors, phone._errors

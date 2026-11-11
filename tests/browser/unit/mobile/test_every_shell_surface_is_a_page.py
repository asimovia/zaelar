"""Every shell surface on the phone is a full-screen PAGE, and the dock has six targets (V2-876 D-A, D-C, D-D).

The operator, looking at the store screenshots (2026-11-11): «no ocupan full screen, queda vacío por arriba y parece un
contenido que sube desde abajo y se puede minimizar». So: chat, menu, apps, settings, feedback and the AI-services
question each take the screen from the status bar to the dock, with one header (‹ · title · ×), a body that scrolls
to its last row, no handle, nothing stacked; the dock is ≡ · chat · apps | orb | mic · speaker; feedback is a row of
the menu page and the wake word a row of Settings; the apps page is a grid where every app wears its own icon.

RENDERED: the real surfaces from `shell/mobile-surfaces.js`, the real Deck and the real stylesheets, in Chromium at
393×852 with touch, in Spanish.
"""
from __future__ import annotations

import json

import pytest

from tests.browser.unit.mobile.phone_page import PACK, H, W, open_phone, shot

ES = PACK["es"]
_APPS = ["agenda", "clock", "contactos", "documento", "fotos", "imagenes", "map", "markets", "mensajeria", "musica",
         "results", "search", "timer", "youtube"]
_REGISTRY = {"registry": [{"id": a, "name": ES.get(f"widgets.{a}.name", a.title()), "surface": "user",
                           "origin": "builtin"} for a in _APPS]
             + [{"id": "mi-dia", "name": "Mi día", "surface": "user", "origin": "user"},
                {"id": "chat", "name": "Chat", "surface": "system", "origin": "system"}]}
_STUB = "export function render(el) { el.innerHTML = '<p class=\"stub\">ok</p>'; }"


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    if path.endswith("/widget.js"):
        return route.fulfill(status=200, content_type="text/javascript", body=_STUB)
    body = _REGISTRY if path == "/registry" else {"widgets": [{"id": a} for a in _APPS]} if path in ("", "/") else {}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


SETUP = """
  const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
  const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
  window.__deck = new Deck(stage);
  const { MOBILE_SURFACES } = await import('/frontend/mobile/app/shell/mobile-surfaces.js?v=4');
  for (const id of ['dock', 'chat', 'menu', 'apps', 'settings', 'feedback', 'ai-consent'])
    document.body.append(MOBILE_SURFACES.find(s => s.id === id).comp());
  window.__apps = await import('/frontend/mobile/app/shell/AppsPane.js?v=2');
  window.__consent = await import('/frontend/mobile/app/shell/ai-consent.js?v=1');
  const store = window.__store;
  window.__pages = await import('/frontend/mobile/app/shell/pages.js?v=1');
  window.__pages.onePageAtATime();          // main.js's rule
  window.__opened = [];
  document.addEventListener('hb:open-card', e => window.__opened.push(e.detail.id));
  // a cloud account with processes running, so the menu page is as long as it gets
  store.setCloudProfile(true);
  store.setEnergy({ cloud: true, known: true, balance: 61, capacity: 400 });
"""

OPENERS = {
    "chat": "s => s.setChatOpen(true)",
    "menu": "s => s.setMobileMenuOpen(true)",
    "apps": "s => window.__apps.setAppsOpen(true)",
    "settings": "s => s.setMobileSettingsOpen(true)",
    "feedback": "s => s.setMobileFeedbackOpen(true)",
    "consent": "s => window.__consent.setSheetOpen(true)",
}


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP, routes=[(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets)]) as pg:
        pg.wait_for_timeout(300)
        yield pg


def _only(pg, name):
    pg.evaluate("""() => { const s = window.__store; s.setChatOpen(false); s.setMobileMenuOpen(false);
        s.setMobileSettingsOpen(false); s.setMobileFeedbackOpen(false); window.__apps.setAppsOpen(false);
        window.__consent.setSheetOpen(false); }""")
    pg.evaluate(f"() => ({OPENERS[name]})(window.__store)")
    pg.wait_for_timeout(260)


def _geom(pg, name):
    return pg.evaluate("""n => { const p = document.querySelector(`.zm-page[data-page="${n}"]`);
        const r = p.getBoundingClientRect(), d = document.querySelector('.zm-dock').getBoundingClientRect();
        const body = p.querySelector('.zm-page-b') || p.querySelector('.zm-msgs');
        if (body) body.scrollTop = body.scrollHeight;
        const kids = [...(body ? body.querySelectorAll('button, .zm-row, form, input') : [])]
          .filter(e => e.getBoundingClientRect().height > 0);
        const last = kids.length ? kids[kids.length - 1].getBoundingClientRect() : null;
        const head = p.querySelector('.zm-page-h').getBoundingClientRect();
        return {top: r.top, bottom: r.bottom, left: r.left, right: r.right, dockTop: d.top,
                headH: head.height, lastBottom: last ? last.bottom : null,
                open: [...document.querySelectorAll('.zm-page.open')].map(e => e.dataset.page),
                btns: [...p.querySelectorAll('.zm-page-h button')].map(b => {
                  const q = b.getBoundingClientRect(); return [q.width, q.height]; })}; }""", name)


@pytest.mark.parametrize("name", list(OPENERS))
def test_each_surface_is_a_full_screen_page_with_its_last_row_reachable(phone, name):
    _only(phone, name)
    g = _geom(phone, name)
    assert g["open"] == [name], f"one page at a time: {g['open']}"
    assert g["top"] == 0 and g["left"] == 0 and g["right"] == W, f"{name} is not the whole width from the top: {g}"
    assert abs(g["bottom"] - g["dockTop"]) <= 1, f"{name} must end at the dock's top edge: {g}"
    assert g["btns"] and all(w >= 44 and h >= 44 for w, h in g["btns"]), f"{name} header targets: {g['btns']}"
    if g["lastBottom"] is not None:
        assert g["lastBottom"] <= g["dockTop"] + 1, f"{name}: the last row is hidden under the dock: {g}"
    shot(phone, f"pr2-page-{name}")


def test_no_bottom_sheet_exists(phone):
    assert phone.evaluate("() => document.querySelectorAll('.zm-sheet, .zm-sheet-grab, .zm-sheet-h').length") == 0
    css = phone.evaluate("() => [...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch (_) "
                         "{ return []; } }).map(r => r.cssText).join('\\n')")
    assert "zm-sheet" not in css and "--zm-sheet-max" not in css


def test_settings_replaces_the_menu_and_back_returns_to_it(phone):
    _only(phone, "menu")
    phone.tap(f".zm-page[data-page='menu'] .zm-row:has-text('{ES['mobile.settings']}')")
    phone.wait_for_timeout(250)
    assert _geom(phone, "settings")["open"] == ["settings"], "settings never stacks on the menu"
    phone.tap(".zm-page[data-page='settings'] .zm-page-back")
    phone.wait_for_timeout(250)
    assert _geom(phone, "menu")["open"] == ["menu"]
    phone.evaluate("() => window.__store.setMobileFeedbackOpen(true)")
    assert phone.evaluate("() => window.__pages.backFromPage()") is True
    phone.wait_for_timeout(100)
    assert _geom(phone, "menu")["open"] == ["menu"], "the platform's back from feedback returns to the ☰ page"


def test_feedback_is_a_row_of_the_menu_page_with_its_thumbs_inside(phone):
    _only(phone, "menu")
    phone.tap(f".zm-page[data-page='menu'] .zm-row:has-text('{ES['feedback.title']}')")
    phone.wait_for_timeout(250)
    g = _geom(phone, "feedback")
    assert g["open"] == ["feedback"]
    assert phone.evaluate("() => document.querySelectorAll('.zm-page[data-page=\"feedback\"] .zm-fb-ic.up, "
                          ".zm-page[data-page=\"feedback\"] .zm-fb-ic.down').length") == 2


def test_the_wake_word_is_a_row_of_settings(phone):
    _only(phone, "settings")
    rows = phone.evaluate("() => [...document.querySelectorAll('.zm-page[data-page=\"settings\"] .zm-row b')].map(b => b.textContent)")
    assert any(r.startswith(ES["mobile.wake_word"].split("«")[0].strip()) for r in rows), rows


def test_the_dock_is_six_targets_of_44(phone):
    _only(phone, "chat")
    phone.evaluate("() => window.__store.setChatOpen(false)")
    d = phone.evaluate("""() => { const d = document.querySelector('.zm-dock');
        const vis = [...d.querySelectorAll('button')].filter(b => b.getBoundingClientRect().width > 0);
        return {n: vis.length, sizes: vis.map(b => { const r = b.getBoundingClientRect(); return [r.width, r.height]; }),
                sides: [...d.querySelectorAll('.zm-side')].map(s => s.querySelectorAll('button').length),
                apps: !!d.querySelector('[data-ctl="apps"]')}; }""")
    assert d["n"] == 6, d
    assert all(w >= 44 and h >= 44 for w, h in d["sizes"]), d
    assert d["sides"] == [3, 2] and d["apps"], d


def test_the_apps_page_is_a_grid_where_every_app_wears_its_own_icon(phone):
    _only(phone, "apps")
    phone.wait_for_selector(".zm-apps-grid .zm-app", timeout=5000)
    g = phone.evaluate("""() => [...document.querySelectorAll('.zm-apps-grid .zm-app')].map(a => ({
        id: a.dataset.app, name: a.querySelector('b').textContent, line: (a.querySelector('small') || {}).textContent || '',
        icon: a.querySelector('.zm-app-ic').textContent + '|' + a.querySelector('.zm-app-ic').style.getPropertyValue('--tile'),
        w: a.getBoundingClientRect().width, h: a.getBoundingClientRect().height}))""")
    ids = [x["id"] for x in g]
    assert set(ids) == set(_APPS) | {"mi-dia"} and "chat" not in ids, ids
    assert len({x["icon"] for x in g}) == len(g), "two apps share an icon"
    assert all(x["w"] >= 44 and x["h"] >= 44 for x in g)
    assert next(x for x in g if x["id"] == "clock")["line"] == ES["widgets.clock.about"]
    assert next(x for x in g if x["id"] == "mi-dia")["line"] == "", "no line is invented for an app that has none"
    cols = phone.evaluate("() => getComputedStyle(document.querySelector('.zm-apps-grid')).gridTemplateColumns.split(' ').length")
    assert cols == 3, cols
    shot(phone, "pr2-apps-grid")
    phone.tap(".zm-apps-grid .zm-app[data-app='clock']")
    phone.wait_for_timeout(300)
    assert phone.evaluate("() => window.__opened") == ["clock"]
    assert _geom(phone, "apps")["open"] == [], "opening an app closes the page and shows the app"


def test_typing_in_the_chat_page_lays_it_over_the_keyboard(phone):
    phone.evaluate("async () => { const k = await import('/frontend/mobile/app/shell/keyboard.js?v=2'); k.initKeyboard(); }")
    _only(phone, "chat")
    phone.focus(".zm-page[data-page='chat'] .zm-compose input")
    phone.set_viewport_size({"width": W, "height": H - 336})
    phone.wait_for_timeout(250)
    st = phone.evaluate("""() => ({kbd: document.documentElement.dataset.kbd || '',
        dock: getComputedStyle(document.querySelector('.zm-dock')).display,
        h: Math.round(document.querySelector('.zm-page[data-page="chat"]').getBoundingClientRect().height)})""")
    phone.evaluate("() => document.activeElement.blur()")
    phone.set_viewport_size({"width": W, "height": H})
    phone.wait_for_timeout(200)
    assert st == {"kbd": "page", "dock": "none", "h": H - 336}, st


def test_no_script_error(phone):
    assert not phone._errors, phone._errors

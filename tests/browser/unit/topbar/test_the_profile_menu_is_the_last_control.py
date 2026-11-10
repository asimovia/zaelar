"""The 👤 profile icon is the LAST control of the top bar and opens a menu of the deployment's two pages, RENDERED.

Operator, 2026-11-10: the profile icon moves to the far right of the bar, and clicking it opens a small menu with
«Private area» (the account page, new tab) and «Log out» (ends the session and lands on the deployment's login). Both
urls come from `/api/config` (`account_url`, `logout_url`); an item whose url is unset is not drawn, and with neither
the icon is not drawn at all — a self-hosted engine has no account and no login. The phone's ☰ menu carries the same
«Log out» row under the same condition.

Mounted in Chromium from the real TopBar / MenuSheet with the shipped bundles. Disarms (seen red 2026-11-10):
`ProfileMenu()` moved back before the memory icon → the order test; the `logout` item pushed unconditionally in
`profileItems` → the unset-url test; the `store.logoutUrl()` gate dropped from `MenuSheet.js` → the phone test.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.daemon.harness import BUNDLES, open_page

pytest.importorskip("playwright.sync_api")

ACCOUNT = "https://accounts.example.test/account"
LOGOUT = "https://accounts.example.test/logout"

_MOUNT_BAR = """async ([cloud, account, logout]) => {
  const { TopBar } = await import('/frontend/app/components/TopBar.js?v=2');
  document.body.append(TopBar());
  window.__store.setCloudProfile(cloud);
  window.__store.setAccountUrl(account);
  window.__store.setLogoutUrl(logout);
  await new Promise(r => setTimeout(r, 50));
}"""

# The bar's controls as the eye reads them: every visible button of the row, left to right.
_READ_BAR = """() => {
  const row = document.querySelector('.trw .tr');
  const shown = [...row.querySelectorAll('button')].filter(b => b.offsetParent !== null && b.getBoundingClientRect().width > 0);
  shown.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  const menu = document.querySelector('.pm-menu');
  return {
    order: shown.map(b => b.id || b.className),
    menuOpen: !!(menu && menu.classList.contains('on') && menu.getBoundingClientRect().height > 0),
    items: menu ? [...menu.querySelectorAll('.pm-item')].map(a => ({
      id: a.dataset.item, text: a.innerText.trim(), href: a.getAttribute('href'), target: a.getAttribute('target')})) : [],
  };
}"""


def _bar(server, *, cloud=True, account=ACCOUNT, logout=LOGOUT, lang="es", steps=()):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": {"ok": True, "state": "off"}}, lang=lang)
        pg.evaluate(_MOUNT_BAR, [cloud, account, logout])
        reads = [pg.evaluate(_READ_BAR)]
        for step in steps:
            step(pg)
            pg.wait_for_timeout(50)
            reads.append(pg.evaluate(_READ_BAR))
        errors = list(pg._errors)
        pg._browser.close()
    return reads, errors


def _click_profile(pg):
    pg.click("#acctBtn")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_profile_is_the_last_control_and_opens_both_pages(server, lang):
    b = BUNDLES[lang]
    (closed, opened), errors = _bar(server, lang=lang, steps=[_click_profile])
    assert closed["order"] and closed["order"][-1] == "acctBtn", closed["order"]
    assert not closed["menuOpen"], "the menu opens on a click, not on its own"
    assert opened["menuOpen"]
    assert opened["items"] == [
        {"id": "account", "text": b["topbar.profile.account"], "href": ACCOUNT, "target": "_blank"},
        {"id": "logout", "text": b["topbar.profile.logout"], "href": LOGOUT, "target": None},
    ], opened["items"]
    assert not errors, errors


def test_the_profile_is_last_on_a_self_hosted_bar_too(server):
    """A self-hosted deployment that names a log-out page (a login in front of it) gets the icon, and it is still
    the last control — to the right of ⚙ and Reset, not in the middle of the row."""
    (r,), errors = _bar(server, cloud=False, account="", logout=LOGOUT)
    assert r["order"][-1] == "acctBtn", r["order"]
    assert r["order"][-2:-1] == ["reset"], r["order"]
    assert [i["id"] for i in r["items"]] == ["logout"]
    assert not errors, errors


def test_an_unset_url_draws_no_item_and_neither_draws_no_icon(server):
    (only_account,), _ = _bar(server, logout="")
    assert [i["id"] for i in only_account["items"]] == ["account"]
    (neither,), errors = _bar(server, cloud=False, account="", logout="")
    assert "acctBtn" not in neither["order"], "a self-hosted engine with no account and no login has no profile icon"
    assert neither["items"] == []
    assert not errors, errors


def test_a_press_outside_or_escape_closes_the_menu(server):
    (_, opened, outside, reopened, escaped), errors = _bar(server, steps=[
        _click_profile, lambda pg: pg.mouse.click(5, 600), _click_profile, lambda pg: pg.keyboard.press("Escape")])
    assert opened["menuOpen"] and not outside["menuOpen"]
    assert reopened["menuOpen"] and not escaped["menuOpen"]
    assert not errors, errors


_MOUNT_SHEET = """async (logout) => {
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/mobile/app/styles.css';
  document.head.append(l);
  const { MenuSheet } = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
  document.body.append(MenuSheet());
  window.__store.setCloudProfile(true);
  window.__store.setAccountUrl('""" + ACCOUNT + """');
  window.__store.setLogoutUrl(logout);
  window.__store.setMobileMenuOpen(true);
  await new Promise(r => setTimeout(r, 50));
  const row = document.querySelector('.zm-menu .zm-logout');
  return row ? row.innerText.trim() : null;
}"""


@pytest.mark.parametrize("logout", [LOGOUT, ""])
def test_the_phone_menu_offers_log_out_only_when_the_deployment_names_it(server, logout):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg = open_page(pw, server, {"status": {"ok": True, "state": "off"}}, width=375, height=812, touch=True)
        text = pg.evaluate(_MOUNT_SHEET, logout)
        errors = list(pg._errors)
        pg._browser.close()
    if logout:
        assert text == BUNDLES["es"]["topbar.profile.logout"], text
    else:
        assert text is None, "with no log-out page there is no Log out row"
    assert not errors, errors

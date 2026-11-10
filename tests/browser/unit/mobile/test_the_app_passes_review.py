"""V2-870 — what App Review checks inside the native app, rendered with the real shell modules in Chromium.

The app is the phone shell in a WebView; `window.Capacitor.isNativePlatform()` is the one fact that tells it apart
(here a stub, `?app=1`). Three review rules, each checked in the app AND in a browser (where nothing must change):

  · 3.1.3(f) — no purchase path inside the app: the out-of-Energy notice and the menu's Energy row open the account
    page WITHOUT #buy, and the notice offers «your account», not «top up»; a browser keeps #buy and «top up».
  · 5.1.2(i) — nothing reaches the AI services before a yes: the question opens on load, the voice gate refuses,
    the orb looks disabled; Accept writes the engine's config, and after a reload the yes is still there.
  · 5.1.1(v) — Settings carries «Delete account», opening the account page at #delete in the system browser.
"""
from __future__ import annotations

import json
import os

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ACCOUNT = "https://account.example.org/account"

PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/mobile/app/styles.css">
<script>
  if (new URLSearchParams(location.search).get("app") === "1")
    window.Capacitor = { isNativePlatform: () => true, getPlatform: () => "ios", Plugins: {} };
  window.__opened = [];
  window.open = (u) => { window.__opened.push(String(u)); return null; };
</script>
<button class="zm-orb-btn" id="orb">orb</button>
<script type="module">
  // The SAME ?v= the shell uses: a module imported with another query string is a second instance.
  import { mount } from "/static/app/core/dom.js?v=2";
  import * as store from "/static/app/core/store.js?v=2";
  import * as consent from "/static/mobile/app/shell/ai-consent.js?v=1";
  import { AiConsentSheet } from "/static/mobile/app/shell/AiConsentSheet.js?v=1";
  import { EnergyNotice } from "/static/app/components/EnergyNotice.js?v=1";
  import { MenuSheet } from "/static/mobile/app/shell/MenuSheet.js?v=2";
  import { SettingsSheet } from "/static/mobile/app/shell/SettingsSheet.js?v=2";
  store.setCloudProfile(true);
  store.setAccountUrl("%s");
  store.setEnergy({ cloud: true, known: true, balance: 0, capacity: 400, exhausted: { reason: "balance_depleted" } });
  mount(AiConsentSheet()); mount(EnergyNotice()); mount(MenuSheet()); mount(SettingsSheet());
  const cfg = await fetch("/api/config").then((r) => r.json());
  consent.loadFrom(cfg);
  window.__consent = consent;
  window.__ready = true;
</script>""" % ACCOUNT


@pytest.fixture()
def browser_page():
    pw = pytest.importorskip("playwright.sync_api")
    engine = {"ai_providers": False, "posts": []}
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 — no browser on this machine is a skip, not a failure
            pytest.skip(f"chromium unavailable: {e}")
        ctx = browser.new_context(viewport={"width": 390, "height": 800}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()

        def route(r):
            path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
            if path in ("", "page"):
                return r.fulfill(status=200, body=PAGE, headers={"content-type": "text/html; charset=utf-8"})
            if path == "api/config":
                return r.fulfill(status=200, body=json.dumps({"v2": {"consent": {"ai_providers": engine["ai_providers"]}}}),
                                 headers={"content-type": "application/json"})
            if path == "api/config/v2" and r.request.method == "POST":
                body = json.loads(r.request.post_data or "{}")
                engine["posts"].append(body)
                if body.get("section") == "consent":
                    engine["ai_providers"] = bool(body["patch"]["ai_providers"])
                return r.fulfill(status=200, body=json.dumps({"ok": True}), headers={"content-type": "application/json"})
            if path.startswith(("api/", "events")):
                return r.fulfill(status=404, body="")
            fp = os.path.join(ENGINE, "frontend", path[len("static/"):]) if path.startswith("static/") else ""
            if not fp or not os.path.isfile(fp):
                return r.fulfill(status=404, body="")
            ct = "text/css" if fp.endswith(".css") else "application/javascript"
            with open(fp, "rb") as fh:
                r.fulfill(status=200, body=fh.read(), headers={"content-type": ct})

        pg.route("**/*", route)

        def open_(app: bool):
            pg.goto("http://phone.test/page" + ("?app=1" if app else ""))
            pg.wait_for_function("window.__ready === true", timeout=15000)
            return pg

        yield open_, engine
        browser.close()


def test_no_purchase_path_inside_the_app_and_unchanged_in_a_browser(browser_page) -> None:
    open_, _ = browser_page
    pg = open_(True)
    a = pg.locator(".en-btn.primary")
    assert a.get_attribute("href") == ACCOUNT, "inside the app the notice opens the account page, never #buy"
    assert a.get_attribute("target") == "_blank", "a new window leaves the app for the system browser"
    assert a.inner_text() == "energy.out.account"
    pg.locator(".zm-energy").evaluate("el => el.click()")
    assert pg.evaluate("window.__opened") == [ACCOUNT]

    pg = open_(False)
    assert pg.locator(".en-btn.primary").get_attribute("href") == ACCOUNT + "#buy"
    assert pg.locator(".en-btn.primary").inner_text() == "energy.out.top_up"
    pg.locator(".zm-energy").evaluate("el => el.click()")
    assert pg.evaluate("window.__opened") == [ACCOUNT + "#buy"]


def test_nothing_reaches_the_ai_services_before_a_yes_and_the_yes_survives_a_reload(browser_page) -> None:
    open_, engine = browser_page
    pg = open_(True)
    assert pg.locator(".zm-consent").get_attribute("class").endswith(" open"), "asked on load, before any turn"
    assert pg.evaluate("document.documentElement.classList.contains('zm-consent-pending')")
    assert pg.evaluate("getComputedStyle(document.getElementById('orb')).opacity") == "0.45"
    assert pg.evaluate("(() => { let ran = false; window.__consent.gate(() => { ran = true; }); return ran; })()") is False

    pg.locator(".zm-consent .zm-ghost").click()          # «Not now»: the sheet closes, the gate still refuses
    assert not pg.locator(".zm-consent").get_attribute("class").endswith(" open")
    pg.evaluate("window.__consent.gate(() => {})")       # a tap on the orb asks again
    assert pg.locator(".zm-consent").get_attribute("class").endswith(" open")

    pg.locator(".zm-consent .zm-primary").click()        # Accept
    pg.wait_for_function("!document.documentElement.classList.contains('zm-consent-pending')")
    assert engine["posts"][-1] == {"section": "consent", "patch": {"ai_providers": True}}
    assert pg.evaluate("(() => { let ran = false; window.__consent.gate(() => { ran = true; }); return ran; })()") is True

    pg = open_(True)                                     # reload: the engine remembers
    assert not pg.locator(".zm-consent").get_attribute("class").endswith(" open")
    assert not pg.evaluate("document.documentElement.classList.contains('zm-consent-pending')")


def test_a_browser_is_never_asked(browser_page) -> None:
    open_, engine = browser_page
    pg = open_(False)
    assert not pg.locator(".zm-consent").get_attribute("class").endswith(" open")
    assert pg.evaluate("(() => { let ran = false; window.__consent.gate(() => { ran = true; }); return ran; })()") is True
    assert engine["posts"] == []


def test_settings_offers_delete_account_and_withdrawal_only_in_the_app(browser_page) -> None:
    open_, engine = browser_page
    pg = open_(True)
    row = pg.locator(".zm-settings .zm-row", has_text="mobile.delete_account")
    assert row.count() == 1
    row.evaluate("el => el.click()")
    assert pg.evaluate("window.__opened") == [ACCOUNT + "#delete"]
    assert pg.locator(".zm-settings", has_text="consent.settings_label").count() == 1

    pg = open_(False)
    assert pg.locator(".zm-settings .zm-row", has_text="mobile.delete_account").count() == 0
    assert pg.locator(".zm-settings", has_text="consent.settings_label").count() == 0


def test_the_engine_keeps_the_answer_as_a_setting_that_starts_at_no() -> None:
    from config import v2
    assert v2.set_keys("consent") == frozenset({"ai_providers"})
    assert v2._DEFAULTS["consent"]["ai_providers"] is False, "a fresh engine has no yes until the person gives it"

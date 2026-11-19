"""Under 5 % of the cycle's Energy, a corner card warns BEFORE the agent stops — never a modal (operator, 2026-11-19).

He ran out in the middle of an errand: the first word about Energy was the out-of-energy notice, when the agent had
already stopped. Rendered, with the REAL component (`components/EnergyLow.js`) and its CSS:
  * at 4 % it shows, translated, saying that nothing is lost at zero; the centre of the screen stays clickable;
  * at 6 %, at zero with the stop in place (the out-of-energy notice speaks then), or on self-host, it does not;
  * closed, it stays closed until a top-up lifts the balance above the line and it drops under it again.
Disarm (in this file): the component served with its threshold at 0 — the 4 % check must fail.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
COMP = ENGINE / "frontend/app/components/EnergyLow.js"
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))
THRESHOLD = "export const LOW_SHARE = 0.05;"


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _page(browser, port, src: str | None = None):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _ES})))
    if src is not None:
        pg.route("**/components/EnergyLow.js*", lambda r: r.fulfill(status=200, content_type="text/javascript", body=src))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
        window.__store = await import('/frontend/app/core/store.js?v=2');
        const m = await import('/frontend/app/components/EnergyLow.js?v=1');
        document.body.append(m.EnergyLow());
        window.__set = (e) => window.__store.setEnergy({ cloud: true, known: true, capacity: 1000, ...e });
    }""")
    pg.wait_for_timeout(300)   # the stylesheets
    pg._errors = errors
    return pg


READ = """() => { const c = document.querySelector('.en-low'); const r = c.getBoundingClientRect();
  const mid = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
  return { shown: getComputedStyle(c).display !== 'none' && r.width * r.height > 2000,
           text: c.innerText, blocksCentre: !!(mid && c.contains(mid)), right: r.right, top: r.top }; }"""


def test_under_five_percent_a_corner_card_warns_and_nothing_is_blocked(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate("() => window.__set({ balance: 40 })")
    st = pg.evaluate(READ)
    assert st["shown"], f"at 4 % the warning shows: {st}"
    assert _ES["energy.low.title"] in st["text"] and "memoria" in st["text"], st
    assert not st["blocksCentre"], "a corner card, never a modal over what he is doing"
    for e, why in [({"balance": 60}, "6 % is not low"), ({"balance": 0, "exhausted": {"reason": "balance_depleted"}},
                   "at zero the out-of-energy notice speaks"), ({"balance": 40, "cloud": False}, "self-host has no balance")]:
        pg.evaluate("(e) => window.__set(e)", e)
        assert not pg.evaluate(READ)["shown"], why
    assert not pg._errors, pg._errors
    pg.close()


def test_closed_it_stays_closed_until_a_top_up_and_a_new_drop(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate("() => window.__set({ balance: 40 })")
    pg.click(".en-low-x")
    assert not pg.evaluate(READ)["shown"], "closing closes it"
    pg.evaluate("() => window.__set({ balance: 30 })")
    assert not pg.evaluate(READ)["shown"], "it keeps spending under the line: closed stays closed"
    pg.evaluate("() => window.__set({ balance: 500 })")
    pg.evaluate("() => window.__set({ balance: 45 })")
    assert pg.evaluate(READ)["shown"], "after a top-up, the next drop under the line warns again"
    pg.close()


def test_a_warning_that_never_fires_is_caught(browser_and_port):
    src = COMP.read_text(encoding="utf-8")
    assert THRESHOLD in src, "the line this disarm moves is gone — update the disarm"
    b, port = browser_and_port
    pg = _page(b, port, src=src.replace(THRESHOLD, "export const LOW_SHARE = 0;"))
    pg.evaluate("() => window.__set({ balance: 40 })")
    assert not pg.evaluate(READ)["shown"], "the disarm stayed green"
    pg.close()

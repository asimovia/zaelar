"""The phone shell RENDERED for a browser unit test: the real stylesheets and modules, served from the engine's own tree
by a static server, in Chromium at 393×852 with touch (iPhone 15/16/17), with the engine's `/api/**` answered by stubs.

`open_phone(setup_js)` yields a page where `setup_js` (an async function body) has run after the language bundle is
loaded; it can import any module by its `/frontend/...` path. `routes` adds more stubs (`(matcher, handler)` pairs,
added after the catch-all so they win). Screenshots go to `$PHONE_SHOTS` when it is set (never committed).
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
W, H = 393, 852
SHOTS = Path(os.environ["PHONE_SHOTS"]) if os.environ.get("PHONE_SHOTS") else None
PACK = {lang: json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8")) for lang in ("es", "en")}

CSS = ["/frontend/app/core/palette.css", "/frontend/app/core/shared-surfaces.css",
       "/frontend/app/core/components.css", "/frontend/mobile/app/styles.css"]


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@contextlib.contextmanager
def open_phone(setup_js: str, *, lang: str = "es", routes=(), width: int = W, height: int = H):
    pw_mod = pytest.importorskip("playwright.sync_api")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    bundle = json.dumps({"strings": PACK[lang]})
    try:
        with pw_mod.sync_playwright() as pw:
            try:
                b = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001 — no browser on this machine is a skip, not a failure
                pytest.skip(f"chromium unavailable: {e}")
            ctx = b.new_context(viewport={"width": width, "height": height}, has_touch=True, is_mobile=True)
            pg = ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            posts: list[dict] = []

            def api(r):
                if r.request.method == "POST":
                    try:
                        posts.append({"url": r.request.url.split("?")[0].split(str(port), 1)[1],
                                      "body": json.loads(r.request.post_data or "{}")})
                    except Exception:  # noqa: BLE001
                        pass
                r.fulfill(status=200, content_type="application/json", body="{}")

            # The catch-all FIRST: Playwright gives the LAST matching route priority.
            pg.route("**/api/**", api)
            pg.route(lambda url: "/widgets" in url and "/frontend/" not in url,
                     lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=bundle))
            for match, handler in routes:
                pg.route(match, handler)
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async ([css, lang, setup]) => {
                document.body.innerHTML = '';
                const vp = document.createElement('meta'); vp.name = 'viewport';
                vp.content = 'width=device-width, initial-scale=1, viewport-fit=cover'; document.head.append(vp);
                for (const h of css) { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h;
                                       document.head.append(l); }
                await new Promise(r => setTimeout(r, 300));
                const i18n = await import('/frontend/app/core/i18n.js?v=1');
                await i18n.loadBundle(lang); if (i18n.applyLang) await i18n.applyLang(lang);
                window.__store = await import('/frontend/app/core/store.js?v=2');
                await (new Function('return (async () => {' + setup + '})()'))();
            }""", [CSS, lang, setup_js])
            pg._errors = errors
            pg._posts = posts
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def shot(pg, name: str) -> None:
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(SHOTS / f"{name}.png"))

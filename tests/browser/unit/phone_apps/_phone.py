"""Mount one app the way the phone deck does — inside `.zm-scroll`, at 393×852 — off a static server of the engine."""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
from contextlib import contextmanager

from tests.waiting import until_sync

ENGINE = pathlib.Path(__file__).resolve().parents[4]

PAGE = ("<link rel='stylesheet' href='/frontend/app/core/palette.css'>"
        "<link rel='stylesheet' href='/frontend/app/core/components.css'>"
        "<style>body{margin:0;background:#1F242B}</style>"
        "<div class='zm-scroll' style='width:393px;height:780px;overflow:auto;box-sizing:border-box;padding:0 12px;"
        "display:flex;flex-direction:column'><div id='host' style='flex:1 1 auto;min-height:0;display:flex;"
        "flex-direction:column'></div></div>")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@contextmanager
def phone(widget_id: str):
    """A page with `window.__render(data)` mounting `widgets/<id>/widget.js` in the phone card, `window.__acts`
    recording every `ctx.action`."""
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 393, "height": 852})
            pg.goto(f"http://127.0.0.1:{port}/widgets/{widget_id}/")
            pg.set_content(PAGE)
            pg.evaluate("""async (src) => { const mod = await import(src); window.__acts = [];
                const ctx = { action(a, p){ window.__acts.push([a, p || {}]); return Promise.resolve({ok: true}); },
                              close(){}, top(){}, openConnector(){}, lang: 'en', running: true };
                window.__render = (d) => mod.render(document.getElementById('host'), JSON.parse(JSON.stringify(d)), ctx);
            }""", f"http://127.0.0.1:{port}/widgets/{widget_id}/widget.js")
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)

"""The phone pass — every native app opened in the REAL mobile shell on an iPhone 14 (WebKit) and a Pixel 7
(Chromium), screenshotted and measured, tab by tab (V2-813).

WHY THIS EXISTS. `render_widgets_on_a_phone.py` mounts each widget in a box the size of a phone and measures it; it
passed all sixteen apps on 2026-10-26 while the operator's own iPhone showed youtube's header broken into two rows,
because the break came from the SHELL's touch floor meeting the widget, and only the real shell has both. This opens
`/m` itself, so what it shows is what the phone shows.

ISOLATED: a preview of the engine's routers on a free port, with `ZAELAR_WORKSPACE`/`ZAELAR_DB` in a temp folder
that holds a COPY of each app's small state files. The LiveKit router is not mounted and every session/token
request is aborted, so the operator's engine, his voice and his data are never touched.

Run (all apps, or some), then LOOK at the screenshots — the numbers alone passed what the pictures did not:

    ./.venv/bin/python tests/browser/e2e/mobile/phone_pass.py
    ./.venv/bin/python tests/browser/e2e/mobile/phone_pass.py youtube results --tabs

Screenshots land in `tests/browser/e2e/mobile/_out/phone_pass/<device>/`. Exit code 1 when an app throws, the page
scrolls sideways, something escapes the screen, an input is under 16px, or a tab strip wraps.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out", "phone_pass")
DEVICES = (("iPhone 14", "webkit", {"width": 390, "height": 750}),   # Safari's visible area, bars excluded
           ("Pixel 7", "chromium", None))
MAX_STATE = 2 * 1024 * 1024

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api, voice_api, canvas_api, screens_api
from widgets import server_api as widgets_api
app = FastAPI()
for r in (pages.router, i18n_api.router, voice_api.router, canvas_api.router, screens_api.router, widgets_api.router):
    app.include_router(r)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

MEASURE = """() => {
  const vw = innerWidth, out = {docW: document.documentElement.scrollWidth, vw, escape: [], tinyIn: [], wrapped: []};
  const card = document.querySelector('.zm-card.live') || document;
  for (const el of card.querySelectorAll('*')) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (r.right > vw + 1 || r.left < -1) {
      let held = false;
      for (let p = el.parentElement; p; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (/auto|scroll|hidden/.test(ox) && p.getBoundingClientRect().right <= vw + 1) { held = true; break; }
      }
      if (!held) out.escape.push(el.tagName.toLowerCase() + '.' + String(el.className || '').slice(0, 30));
    }
  }
  for (const el of card.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea,select'))
    if (parseFloat(getComputedStyle(el).fontSize) < 16) out.tinyIn.push(String(el.className || el.tagName));
  for (const t of card.querySelectorAll('[role=tablist]')) {
    const kids = [...t.children].filter(c => c.getBoundingClientRect().height);
    const mids = new Set(kids.map(c => { const b = c.getBoundingClientRect(); return Math.round((b.top + b.bottom) / 2 / 8); }));
    if (mids.size > 1) out.wrapped.push(String(t.className));
  }
  out.escape = out.escape.slice(0, 6); return out; }"""


def _ids() -> list[str]:
    root = os.path.join(ENGINE, "widgets")
    return sorted(n for n in os.listdir(root) if not n.startswith(("_", "."))
                  and os.path.isfile(os.path.join(root, n, "widget.js"))
                  and os.path.isfile(os.path.join(root, n, "manifest.json")))


def _workspace(ids) -> str:
    """A temp workspace holding a COPY of each app's small top-level state files — never the originals."""
    ws = tempfile.mkdtemp(prefix="phone-pass-")
    for wid in ids:
        src = os.path.join(ENGINE, "widgets", "_data", wid)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(ws, "widgets", "_data", wid)
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(src):
            f = os.path.join(src, n)
            if os.path.isfile(f) and os.path.getsize(f) <= MAX_STATE:
                shutil.copy2(f, dst)
    return ws


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _bad(m: dict) -> bool:
    return bool(m.get("error") or m.get("errors") or m["escape"] or m["tinyIn"] or m["wrapped"] or m["docW"] > m["vw"])


def main() -> int:
    from playwright.sync_api import sync_playwright
    ids = [a for a in sys.argv[1:] if not a.startswith("--")] or _ids()
    tabs = "--tabs" in sys.argv
    ws = _workspace(ids)
    port = _free_port()
    env = {**os.environ, "ZAELAR_LANGUAGE_GATE": "0", "ZAELAR_WORKSPACE": ws, "ZAELAR_DB": os.path.join(ws, "zaelar.db")}
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report: dict[str, dict] = {}
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError:
                time.sleep(0.5)
        else:
            print("preview server never came up"); return 2
        with sync_playwright() as p:
            for dev, engine, viewport in DEVICES:
                d = dict(p.devices[dev]); d.pop("default_browser_type", None)
                if viewport:
                    d["viewport"] = viewport
                tag = dev.replace(" ", "")
                os.makedirs(os.path.join(OUT, tag), exist_ok=True)
                br = getattr(p, engine).launch()
                ctx = br.new_context(**d)
                ctx.add_init_script("try{localStorage.setItem('hb_lang','es');localStorage.setItem('hb_device_id','phonepass');"
                                    "sessionStorage.setItem('hb_first_run_takeover','1')}catch(_){}")
                ctx.route("**/*", lambda r: r.abort() if any(k in r.request.url for k in
                          ("/api/session/", "/api/token", "/api/livekit", "livekit.cloud", "wss:")) else r.continue_())
                pg = ctx.new_page()
                errs: list[str] = []
                pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
                pg.goto(f"http://127.0.0.1:{port}/m", wait_until="domcontentloaded")
                pg.wait_for_timeout(3000)
                for wid in ids:
                    del errs[:]
                    pg.evaluate("() => document.querySelectorAll('.boot-ovl,.lang-onb,.lang-onb-veil,.zm-held')"
                                ".forEach(e => e.remove())")
                    try:
                        pg.evaluate("async (id) => { for (const o of window.__zaelarDeck.list()) window.__zaelarDeck.close(o);"
                                    " await window.__zaelarDeck.show(id); }", wid)
                    except Exception as e:  # noqa: BLE001 — an app that throws is the finding
                        report[f"{tag}/{wid}"] = {"error": str(e)[:200]}; continue
                    pg.wait_for_timeout(1800)
                    pg.screenshot(path=os.path.join(OUT, tag, f"{wid}.png"))
                    m = pg.evaluate(MEASURE); m["errors"] = list(errs)
                    report[f"{tag}/{wid}"] = m
                    if not tabs:
                        continue
                    strip = pg.locator(".zm-card.live [role=tablist] > button")
                    for k in range(strip.count()):
                        strip.nth(k).scroll_into_view_if_needed()
                        strip.nth(k).click(timeout=3000)
                        pg.wait_for_timeout(900)
                        pg.screenshot(path=os.path.join(OUT, tag, f"{wid}_tab{k}.png"))
                        mt = pg.evaluate(MEASURE); mt["errors"] = list(errs)
                        report[f"{tag}/{wid}_tab{k}"] = mt
                br.close()
    finally:
        proc.terminate()
        shutil.rmtree(ws, ignore_errors=True)
    bad = {k: v for k, v in report.items() if _bad(v)}
    for k in report:
        print(("FAIL " if k in bad else "ok   ") + k + ("  " + json.dumps(
            {x: v for x, v in bad[k].items() if v and x not in ("vw",)}, ensure_ascii=False)[:300] if k in bad else ""))
    print(f"\nscreenshots: {OUT}\n" + (f"{len(bad)} FAILURE(S)" if bad else "ALL OK — now look at the screenshots"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

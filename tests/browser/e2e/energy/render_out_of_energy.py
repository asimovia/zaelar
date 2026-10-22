"""Render the desktop in Chromium with a cloud account that ran OUT of Energy, and MEASURE what a person sees
(V2-785, node 4.247).

WHY RENDERED. Until 2026-10-22 running out of Energy was only SPOKEN; nothing on screen said where to top up. A
flag in the store would pass any source-level test while the notice sat in the DOM with no box, or with the raw
i18n key as its text (a key is truthy), or with a link to nowhere. Everything below needs a browser:

  · the out-of-energy notice is CONNECTED, has AREA, is visible, and speaks translated text;
  · its «Top up» button is a real link to the ENGINE's account url (the one `/api/config` names — no literal in
    the frontend) with the `#buy` fragment, opening in a new tab;
  · closing it closes it;
  · the battery is a keyboard-reachable LINK to the same place, with a translated aria-label.

SELF-CONTAINED AND NON-DESTRUCTIVE: its own preview server (server.pages + /static + server.i18n_api) on a free
port; `/api/config` and `/api/energy` are faked at the network layer with the shapes the engine returns.

Run:  ./.venv/bin/python tests/browser/e2e/energy/render_out_of_energy.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 1280, 900
MIN_AREA = 400
ACCOUNT = "https://account.example.test/account"

PREVIEW = '''
import sys
sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI()
app.include_router(pages.router)
app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

LIFT_VEIL = """() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e => e.remove())"""

MEASURE = """(sel) => {
  const e = document.querySelector(sel);
  if (!e) return { found: false };
  const r = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  return { found: true, connected: e.isConnected, area: Math.round(r.width * r.height), tag: e.tagName,
           visible: cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0.05,
           text: (e.textContent || '').trim(), href: e.getAttribute('href'), target: e.getAttribute('target'),
           aria: e.getAttribute('aria-label') };
}"""

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("preview server never came up")
            return 1
        time.sleep(1.0)
        return run(f"http://127.0.0.1:{port}/")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def run(url):
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": W, "height": H}).new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        cfg = {"cloud_profile": True, "account_url": ACCOUNT}
        energy = {"cloud": True, "known": True, "balance": 0, "capacity": 250, "at": 0,
                  "lease": {"leased": True, "allowed": False}, "account_url": ACCOUNT,
                  "exhausted": {"reason": "energy_lease_exhausted", "at": 1}}
        pg.route("**/api/config", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(cfg)))
        pg.route("**/api/energy", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(energy)))

        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_timeout(3000)             # i18n bundle + the two seeds
        pg.evaluate(LIFT_VEIL)
        pg.wait_for_timeout(300)

        box = pg.evaluate(MEASURE, ".en-ovl.on .en-box")
        check("the out-of-energy notice is painted", bool(box.get("found")),
              "nothing on screen — exactly the state the 2026-10-22 account was left in")
        if box.get("found"):
            check("…connected", bool(box.get("connected")))
            check("…with area", box.get("area", 0) >= MIN_AREA, f"area={box.get('area')}")
            check("…visible", bool(box.get("visible")))
            check("…in translated words, not i18n keys", box.get("text") and "energy." not in box["text"],
                  f"text={box.get('text')!r}")
        btn = pg.evaluate(MEASURE, ".en-ovl.on a.en-btn.primary")
        check("the notice has a Top up link", bool(btn.get("found")))
        if btn.get("found"):
            check("…to the ENGINE's account url, top-up section", btn.get("href") == ACCOUNT + "#buy",
                  f"href={btn.get('href')!r}")
            check("…in a new tab", btn.get("target") == "_blank")
            check("…with area", btn.get("area", 0) >= MIN_AREA // 4, f"area={btn.get('area')}")

        gauge = pg.evaluate(MEASURE, "a.eg")
        check("the battery is a link", bool(gauge.get("found")) and gauge.get("tag") == "A")
        if gauge.get("found"):
            check("…to the top-up section", gauge.get("href") == ACCOUNT + "#buy", f"href={gauge.get('href')!r}")
            check("…with a translated aria-label", bool(gauge.get("aria")) and "energy." not in gauge["aria"],
                  f"aria={gauge.get('aria')!r}")
            pg.focus("a.eg")
            focused = pg.evaluate("() => document.activeElement && document.activeElement.matches('a.eg')")
            check("…reachable from the keyboard", bool(focused))

        if box.get("found"):
            pg.click(".en-ovl.on .en-btn:not(.primary)")
            pg.wait_for_timeout(300)
            check("closing the notice closes it", not pg.evaluate(MEASURE, ".en-ovl.on .en-box").get("found"))

        mine = [e for e in errors if "EnergyNotice" in e or "account-link" in e or "EnergyGauge" in e]
        check("no page error from the new code", not mine, f"{mine}")
        b.close()
    print(f"\n{'FAILED: ' + str(len(fails)) if fails else 'ALL OK'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

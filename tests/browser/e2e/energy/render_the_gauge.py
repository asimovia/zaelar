"""Render the top bar in Chromium with cloud accounts on different plans, and MEASURE the Energy gauge (2026-10-24).

The operator's demo account had 397 Energy and the gauge looked empty; and the gauge sat INSIDE the box of controls,
its bars competing with the icons. Rendered, because a source-level check cannot see either: the gauge must be
OUTSIDE the box and to its left, draw the same number of bars for every plan (by screen width), light «what the
cycle gave minus what was spent» in proportion, keep spent bars as boxes and the rest as placeholders.
Screenshots land in tests/runs/energy-gauge-*.png.

(The harness below is the out-of-energy render's, V2-785.)

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

Run:  ./.venv/bin/python tests/browser/e2e/energy/render_the_gauge.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")))
from tests.waiting import until_sync  # noqa: E402

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
        def up():
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                return True
            except OSError:
                return False
        until_sync(up, "the preview server to answer", timeout_s=30)
        time.sleep(1.0)
        return run(f"http://127.0.0.1:{port}/")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


CASES = [
    # (label, width, balance, capacity, plan) → (bars, lit, spent within the cycle)
    ("free-397-of-500", 1280, 397, 500, {"key": "free", "name": "Free", "scale": 13000, "tier": 0}, (30, 1, 0)),
    ("pulse-half", 1280, 1500, 3000, {"key": "plan_pulse", "name": "Pulse", "scale": 13000, "tier": 2}, (30, 3, 4)),
    ("overdrive-full", 1280, 13000, 13000, {"key": "plan_overdrive", "name": "Overdrive", "scale": 13000, "tier": 4}, (30, 30, 0)),
    ("spark-narrow", 820, 650, 1300, {"key": "plan_spark", "name": "Spark", "scale": 13000, "tier": 1}, (12, 1, 0)),
]

GAUGE = """() => {
  const g = document.querySelector('.trw > .eg');
  const box = document.querySelector('.trw > .tr');
  if (!g || !box) return { found: false, inBox: !!document.querySelector('.tr .eg') };
  const gr = g.getBoundingClientRect(), br = box.getBoundingClientRect();
  const bars = [...g.querySelectorAll('.eg-t')];
  return { found: true, leftOfBox: gr.right <= br.left, inBox: !!box.querySelector('.eg'),
           bars: bars.length, on: g.querySelectorAll('.eg-on').length, spent: g.querySelectorAll('.eg-spent').length,
           free: g.querySelectorAll('.eg-free').length, title: g.getAttribute('title') || '',
           onColor: bars.length && g.querySelector('.eg-on') ? getComputedStyle(g.querySelector('.eg-on')).backgroundImage : '',
           spentBorder: g.querySelector('.eg-spent') ? getComputedStyle(g.querySelector('.eg-spent')).borderTopWidth : '' };
}"""


def run(url):
    errors = []
    os.makedirs(os.path.join(ENGINE, "tests", "runs"), exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, width, balance, cap, plan, (want_bars, want_on, want_spent) in CASES:
            ctx = b.new_context(viewport={"width": width, "height": 700}, color_scheme="dark")
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            cfg = {"cloud_profile": True, "account_url": ACCOUNT}
            energy = {"cloud": True, "known": True, "balance": balance, "capacity": cap, "plan": plan, "at": 0,
                      "lease": {"leased": True, "allowed": True}, "account_url": ACCOUNT, "exhausted": None}
            pg.route("**/api/config", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(cfg)))
            body = json.dumps(energy)
            pg.route("**/api/energy", lambda r, _req=None, body=body: r.fulfill(
                status=200, content_type="application/json", body=body))
            pg.goto(url, wait_until="domcontentloaded")
            pg.wait_for_timeout(3000)
            pg.evaluate(LIFT_VEIL)
            pg.wait_for_timeout(300)
            m = pg.evaluate(GAUGE)
            print(f"[{label}]")
            check("the gauge is painted outside the box of controls", m.get("found") and not m.get("inBox"), f"{m}")
            if m.get("found"):
                check("…to its LEFT", bool(m.get("leftOfBox")), f"{m}")
                check(f"…with {want_bars} bars", m["bars"] == want_bars, f"bars={m['bars']}")
                check(f"…{want_on} lit", m["on"] == want_on, f"on={m['on']}")
                check(f"…{want_spent} spent boxes", m["spent"] == want_spent, f"spent={m['spent']}")
                check("…lit bars have relief (a gradient)", "gradient" in m.get("onColor", ""), m.get("onColor"))
                if want_spent:
                    check("…spent boxes have an edge", m.get("spentBorder") == "1px", m.get("spentBorder"))
                check("…the tooltip says the cycle in words", str(balance) in m["title"] and "energy." not in m["title"],
                      m["title"])
            box = pg.query_selector(".trw")
            if box:
                bb = box.bounding_box()
                pg.screenshot(path=os.path.join(ENGINE, "tests", "runs", f"energy-gauge-{label}.png"),
                              clip={"x": max(0, bb["x"] - 20), "y": 0, "width": min(width, bb["width"] + 40),
                                    "height": bb["y"] + bb["height"] + 16})
            ctx.close()
        mine = [e for e in errors if "EnergyGauge" in e or "TopBar" in e]
        check("no page error from the gauge or the bar", not mine, f"{mine}")
        b.close()
    print(f"\n{'FAILED: ' + str(len(fails)) if fails else 'ALL OK'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

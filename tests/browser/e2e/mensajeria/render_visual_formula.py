"""RENDER check — the messaging widget's visual formula (V2-521, redesigned V2-570; connectors left the card for
⚙ Conectores on 2026-10-04; «where am I» on 2026-10-26).

The header shows EVERY channel (connected bright, unconnected dimmed); a dimmed icon opens ⚙ Conectores on THAT
connector — the same door the voice takes — and the card itself draws no setup screen. The house and the title are
lit on the home; a bright icon applies the platform lens (underline = visible state, not memory), dims the house
and names the section, and a second click clears it. Tolerant of the live engine's connection state: the
dimmed/bright halves each run only when such an icon exists.
"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.getenv("ZAELAR_URL", "http://127.0.0.1:43917")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")
os.makedirs(OUT, exist_ok=True)
problems = []
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.evaluate("window.__zaelarDesktop.show('mensajeria')")
    pg.wait_for_selector(".hb-msg", timeout=10000); pg.wait_for_timeout(800)

    # Start from the home whatever screen the live card was left on (a mail, a draft, a channel).
    for sel in (".hb-msg .mchome", ".hb-msg .hd .homebtn:not(.on)"):
        if pg.query_selector(sel):
            pg.click(sel)
            pg.wait_for_timeout(600)

    # 1) the header shows ALL channels — connected bright, unconnected dimmed
    icons = pg.eval_on_selector_all(".hb-msg .dots .picon",
        "els => els.map(e => ({on: e.classList.contains('on'), title: e.title}))")
    print("header icons:", icons)
    if len(icons) != 3:
        problems.append(f"expected 3 channel icons, got {len(icons)}")
    dimmed = [i for i in icons if not i["on"]]
    pg.screenshot(path=f"{OUT}/vf_1_header.png")

    # 2) the home says it is the home: the house and the title lit
    if not pg.query_selector(".hb-msg .hd .homebtn.on") or not pg.query_selector(".hb-msg .hd .hdtitle.on"):
        problems.append("the home does not light its house and title")

    # 3) clicking a DIMMED icon opens ⚙ Conectores on that connector — the card draws no setup screen of its own
    if dimmed:
        pg.click(".hb-msg .dots .picon:not(.on)")
        pg.wait_for_timeout(800)
        if not pg.query_selector("[data-cx-close]"):
            problems.append("clicking a dimmed icon did not open ⚙ Conectores on that connector")
        if pg.query_selector(".hb-msg .crumb, .hb-msg .chanhead, .hb-msg .wstep"):
            problems.append("the card drew a setup screen of its own")
        pg.screenshot(path=f"{OUT}/vf_2_connect_from_header.png")
        close = pg.query_selector("[data-cx-close]")
        if close:
            close.click()
            pg.wait_for_timeout(400)

    # 4) clicking a BRIGHT icon applies the lens (underline marks it), clicking again removes it
    if any(i["on"] for i in icons):
        pg.click(".hb-msg .dots .picon.on")
        pg.wait_for_timeout(400)
        if not pg.query_selector(".hb-msg .picon.filt"):
            problems.append("the platform lens did not mark the active icon")
        if pg.query_selector(".hb-msg .hd .homebtn.on") or not pg.query_selector(".hb-msg .hd .hdsec"):
            problems.append("inside a section the house stays lit or the section is not named")
        pg.screenshot(path=f"{OUT}/vf_3_lens.png")
        pg.click(".hb-msg .dots .picon.filt")
        pg.wait_for_timeout(300)
        if pg.query_selector(".hb-msg .picon.filt"):
            problems.append("clicking the lensed icon again did not clear the lens")
    b.close()
for p in problems: print("FAIL:", p)
print("visual formula:", "OK" if not problems else "FAILED")
sys.exit(1 if problems else 0)

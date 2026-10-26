"""The mail section is a simplified Gmail: ONE left rail at every width, legible in both themes (V2-807, RENDERED).

The operator's design, approved 2026-10-26: «no hace falta tener un menú header y un menú lateral izquierdo, lo
puedes poner todo en el izquierdo». One rail holds Compose, the Inbox opening into the categories the provider sorts
it by (each with the provider's own unread figure — Primary's 14, never the Inbox's 1603), and every other folder.
The header says only where he is. The rail reads the card's own width: labels on a wide card, icons on a narrow one,
a drawer behind a button that names where he is on a phone-narrow one.

Rendered in a real browser from the real widget module and the real palette, with the actions recorded.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_CARD_CSS = """
  body{margin:0;font-family:-apple-system,system-ui,sans-serif;background:var(--canvas,#eee)}
  .hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;padding:30px 16px 16px;
          overflow:hidden;box-sizing:border-box;background:var(--hb-bg,#fff);border-radius:12px}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
  #w{height:100%}
"""

_FOLDERS = [{"name": "INBOX", "role": "inbox", "label": "INBOX"},
            {"name": "[Gmail]/Starred", "role": "flagged", "label": "Starred"},
            {"name": "[Gmail]/Drafts", "role": "drafts", "label": "Drafts"},
            {"name": "[Gmail]/Sent Mail", "role": "sent", "label": "Sent Mail"},
            {"name": "[Gmail]/All Mail", "role": "all", "label": "All Mail"},
            {"name": "[Gmail]/Spam", "role": "junk", "label": "Spam"},
            {"name": "[Gmail]/Trash", "role": "trash", "label": "Trash"},
            {"name": "Facturas", "role": "", "label": "Facturas"}]
_CATS = [{"key": "primary", "unread": 14}, {"key": "social", "unread": 40}, {"key": "promotions", "unread": 1549},
         {"key": "updates", "unread": 3}]
_ROWS = [{"uid": str(900 - i), "from": f"p{i}@x.com", "fromName": f"Person {i}", "subject": f"Subject number {i}",
          "ts": 1700000000 - i * 3600, "seen": i % 3 == 0} for i in range(14)]


def _data(**mb):
    box = {"folders": _FOLDERS, "folder": "INBOX", "role": "inbox", "category": "primary", "categories": _CATS,
           "counts": {"INBOX": 1603, "[Gmail]/Spam": 4, "Facturas": 2, "[Gmail]/Sent Mail": 0}, "unread": 14,
           "rows": _ROWS, "loading": False, "asked": True, "more": True, "error": "", "open": None, "draft": None}
    box.update(mb)
    return {"platforms": {p: {"status": "connected"} for p in ("whatsapp", "telegram", "email")},
            "items": [], "chats": [], "active_chat": None, "active_items": [], "drafts": {}, "sent": [],
            "mailbox": box, "view": {"platform": "email", "n": int(time.time() * 1000) % 100000, "at": time.time()}}


@pytest.fixture(scope="module")
def _page():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 800})
            page._hb_port = port
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, w=760, h=600, theme=None):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/mensajeria/")
    attr = f" data-theme='{theme}'" if theme else ""
    page.set_content(f"<html{attr}><head><link rel='stylesheet' href='/frontend/app/core/palette.css'>"
                     f"<style>{_CARD_CSS}</style></head><body><div class='hb-win' style='width:{w}px;height:{h}px'>"
                     f"<div class='hb-scroll'><div id='w'></div></div></div></body></html>")
    page.wait_for_function("() => getComputedStyle(document.documentElement).getPropertyValue('--hb-bg').trim()")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?t=' + Math.random());
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve(null); },
                             top: () => {}, openConnector: () => {}, running: true, lang: 'es'};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js", data])


def _calls(page, name):
    return [c[1] for c in page.evaluate("window.__calls") if c[0] == name]


def _visible_labels(page):
    return page.evaluate("""() => [...document.querySelectorAll('.mrail .mnav')]
        .filter(b => b.offsetParent !== null)
        .map(b => [b.querySelector('.mnl').offsetParent ? b.querySelector('.mnl').textContent : '',
                   (b.querySelector('.mfn') || {}).textContent || ''])""")


def test_one_left_rail_holds_every_section_and_the_header_only_says_where_he_is(_page):
    _mount(_page, _data())
    assert _page.locator(".mfolders, .mfoldnav, .mfold").count() == 0, "no second menu across the top"
    assert _page.locator(".hd").count() == 1
    assert _page.locator(".hd .hdsec").inner_text() == "Correo" and _page.locator(".hd .hdcur").inner_text() == "Principal"
    assert _visible_labels(_page) == [["Recibidos", "14"], ["Principal", "14"], ["Social", "40"],
                                      ["Promociones", "1549"], ["Notificaciones", "3"], ["Destacados", ""],
                                      ["Borradores", ""], ["Enviados", ""], ["Todos", ""], ["Spam", "4"],
                                      ["Papelera", ""], ["Facturas", "2"]]
    assert "1603" not in _page.locator(".mrail").inner_text(), "the Inbox counts Primary, as Gmail's badge does"
    assert _page.locator(".mnav.on .mnl").inner_text() == "Principal"
    rail, lst = _page.locator(".mrail").bounding_box(), _page.locator(".mlist").bounding_box()
    assert rail["x"] + rail["width"] <= lst["x"] + 1, "the rail is LEFT of the list"
    assert not _page.locator(".mdrawerbtn").is_visible()
    _page.locator(".mnav", has_text="Promociones").click()
    assert _calls(_page, "mail_folder")[-1] == {"folder": "INBOX", "category": "promotions"}
    _page.locator(".mnav", has_text="Spam").click()
    assert _calls(_page, "mail_folder")[-1] == {"folder": "[Gmail]/Spam"}


def test_a_narrow_card_folds_the_rail_to_icons_that_keep_their_names_and_counts(_page):
    _mount(_page, _data(), w=560)
    rail = _page.locator(".mrail").bounding_box()
    assert rail["width"] < 72, rail
    assert all(lbl == "" for lbl, _ in _visible_labels(_page)), "icons only: the labels are folded away"
    promo = _page.locator(".mnav", has_text="Promociones")
    assert promo.get_attribute("aria-label") == "Promociones (1549)" and promo.get_attribute("title") == "Promociones"
    assert promo.locator(".mfn").is_visible(), "the count stays on the icon"
    lst = _page.locator(".mlist").bounding_box()
    assert lst["width"] > 360, "the list keeps the room the labels gave back"


def test_a_phone_narrow_card_puts_the_rail_in_a_drawer_named_where_he_is(_page):
    _mount(_page, _data(), w=380, h=640)
    assert not _page.locator(".mrail").is_visible()
    btn = _page.locator(".mdrawerbtn")
    assert btn.is_visible() and btn.inner_text().strip() == "Principal"
    btn.click()
    assert _page.locator(".mrail").is_visible()
    assert [l for l, _ in _visible_labels(_page)][:4] == ["Recibidos", "Principal", "Social", "Promociones"]
    _page.locator(".mnav", has_text="Social").click()
    assert _calls(_page, "mail_folder")[-1] == {"folder": "INBOX", "category": "social"}
    assert not _page.locator(".mrail").is_visible(), "a tap in the drawer closes it"
    sw = _page.evaluate("() => { const p = document.querySelector('.hb-scroll'); return p.scrollWidth - p.clientWidth; }")
    assert sw <= 0, "nothing scrolls sideways on a phone"


def test_a_server_that_sorts_nothing_lists_folders_only_with_their_own_counts(_page):
    _mount(_page, _data(category=None, categories=[], counts={"INBOX": 7}, unread=7))
    labels = [l for l, _ in _visible_labels(_page)]
    assert labels[:2] == ["Recibidos", "Destacados"] and "Principal" not in labels
    assert _visible_labels(_page)[0] == ["Recibidos", "7"]
    assert _page.locator(".hd .hdcur").inner_text() == "Recibidos"


# ── legible in both themes (V2-691) ───────────────────────────────────────────────────────────────────────────

def _contrast(page, fg_sel, bg_sel, bg_prop="backgroundColor"):
    return page.evaluate("""([a, b, prop]) => {
      const rgb = s => { const m = s.match(/[\\d.]+/g).map(Number); return m.slice(0, 3); };
      const lum = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
                         return .2126 * r + .7152 * g + .0722 * b; };
      const fg = lum(rgb(getComputedStyle(document.querySelector(a)).color));
      const bg = lum(rgb(getComputedStyle(document.querySelector(b))[prop]));
      return (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05); }""", [fg_sel, bg_sel, bg_prop])


@pytest.mark.parametrize("theme,bg", [(None, "#1f242b"), ("light", "#ffffff")])
def test_the_rail_reads_on_the_real_palette_in_both_themes(_page, theme, bg):
    _mount(_page, _data(), theme=theme)
    assert _page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--hb-bg').trim()") \
        .lower() == bg
    assert _contrast(_page, ".mnav:not(.on) .mnl", ".hb-win") >= 4.5
    assert _contrast(_page, ".mnav.on .mnl", ".hb-win") >= 4.5
    assert _contrast(_page, ".mnav:not(.on) .mfn", ".mnav:not(.on) .mfn") >= 4.5
    assert _contrast(_page, ".mrow .mfrom", ".hb-win") >= 7

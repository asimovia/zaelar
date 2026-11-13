"""The rest of the apps on the phone (V2-876 T5, P-50…P-52), RENDERED in the phone card at 393×852.

The audit of 2026-11-11 found, one screen at a time: the messages header wrapping onto a second row with a stray
divider and the plug in sight (rule 5) and the channel icons twice (dim on the row, big in the empty state); Images
saying its own name again under the header that already says it; a ghost button as the one action of an unconnected
Photos; a blank Document with no request that would fill it (rule 7).
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.phone_apps._phone import phone  # noqa: E402


def _rows(pg, sel: str) -> int:
    """How many lines the visible controls of `sel` take (overlapping vertical bands are one line)."""
    return pg.evaluate("""(s) => { const iv = [...document.querySelectorAll(s)].filter(e => e.getClientRects().length)
        .map(e => e.getBoundingClientRect()).map(r => [r.top, r.bottom]).sort((a, b) => a[0] - b[0]);
        const rows = []; for (const [t, b] of iv) { const l = rows[rows.length - 1];
          if (l && t < l[1] - 2) l[1] = Math.max(l[1], b); else rows.push([t, b]); } return rows.length; }""", sel)


def test_the_messages_header_is_one_row_and_its_channels_fold_into_the_menu():
    with phone("mensajeria") as pg:
        pg.evaluate("window.__render({})")
        pg.wait_for_timeout(250)
        hd = ".hb-msg .hd button, .hb-msg .hd .hdtitle, .hb-msg .hd .picon"
        assert _rows(pg, hd) == 1, "the header never wraps onto a second row"
        assert not pg.locator(".hb-msg .hd .connbtn").is_visible(), "the plug is not on the phone's row (rule 5)"
        assert not pg.locator(".hb-msg .hd .dots").is_visible(), "the channels are not drawn twice"
        pg.click(".hb-msg .hd .hb-bar-more")
        assert pg.locator(".hb-msg .hd .dots").is_visible() and pg.locator(".hb-msg .hd .connbtn").is_visible(), \
            "…they are one tap away, in the bar's menu"


def test_images_never_repeats_its_own_name():
    with phone("imagenes") as pg:
        pg.evaluate("window.__render({})")
        pg.wait_for_timeout(150)
        assert pg.locator(".imghd b").count() == 0, "with nothing named, the header above already says «Images»"
        pg.evaluate("window.__render({query: 'faros de Galicia', items: []})")
        assert pg.inner_text(".imghd b") == "faros de Galicia", "what he asked for still names the screen"


def test_unconnected_photos_offers_one_primary_action():
    with phone("fotos") as pg:
        pg.evaluate("window.__render({})")
        pg.wait_for_timeout(150)
        btn = pg.locator(".fts-cx button")
        assert btn.count() == 1 and "hb-btn--primary" in (btn.get_attribute("class") or "")
        box = btn.bounding_box()
        assert box and box["height"] >= 32


def test_a_blank_document_offers_the_request_that_fills_it():
    with phone("documento") as pg:
        pg.evaluate("window.__render({})")
        pg.wait_for_timeout(150)
        hint = pg.inner_text(".hbd-blank span")
        assert "«" in hint and "»" in hint, f"one sentence and the request that fills it (rule 7): {hint!r}"


def test_the_contact_groups_wear_one_icon_style():
    """The audit: «group icons mix styles (mono heart, 😊 emoji, ⚒︎)» — a Unicode glyph is drawn by the platform's
    font, and iOS turns ☺ into a colour emoji. The natives wear the shell's stroke icons."""
    natives = [{"groupId": g, "name": g, "native": True} for g in ("favorites", "family", "friends", "colleagues")]
    with phone("contactos") as pg:
        pg.evaluate("(rows) => window.__render({contacts: [], groupRows: rows, native_groups: [], count: 0})", natives)
        pg.wait_for_timeout(200)
        icons = pg.evaluate("""() => [...document.querySelectorAll('.ctg .ctgi')]
            .map(i => ({svg: !!i.querySelector('svg'), text: i.textContent.trim()}))""")
        assert icons and all(i["svg"] and not i["text"] for i in icons), icons


def test_a_shelf_is_named_in_his_language_whatever_the_server_called_it():
    """The audit: «folder names in Spanish under an EN UI (Vídeo, Documentos…)». The server names a shelf in one
    language; the app names it by its id («shelf:video») through the language pack, in the tile, the row and the trail."""
    import json as _json
    en = _json.loads((__import__("pathlib").Path(__file__).resolve().parents[4] / "i18n/genesis/en/ui.json").read_text())
    data = {"provider": "local", "connected": True, "mode": "list", "trail": [{"id": "shelf:video", "name": "Vídeo"}],
            "entries": [{"id": "shelf:video", "name": "Vídeo", "kind": "folder"},
                        {"id": "shelf:documents", "name": "Documentos", "kind": "folder"}]}
    with phone("archivos") as pg:
        pg.evaluate("(B) => { window.__t = (k, p) => B[k] || k; }", en)
        pg.evaluate("""(d) => { const host = document.getElementById('host'); return import('/widgets/archivos/widget.js')
            .then(m => m.render(host, d, {action: () => Promise.resolve({ok: true}), close(){}, top(){}, openConnector(){},
                                          t: window.__t, lang: 'en', running: true})); }""", data)
        pg.wait_for_timeout(200)
        text = pg.inner_text("#host")
        assert "Documents" in text and "Video" in text, text
        assert "Documentos" not in text and "Vídeo" not in text, text


@pytest.mark.parametrize("data,want", [
    ({"mode": "blank", "url": "", "rev": 0}, "Pídeme que abra una página"),            # nothing open: the request
    ({"mode": "page", "url": "https://a.example", "rev": 0, "failed": "x"}, "No se pudo abrir"),
    ({"kind": "task", "status": "failed", "shot_rev": 0}, "no dejó captura"),
    ({"mode": "page", "url": "https://a.example", "rev": 0, "loading": True}, "abriendo pestaña"),
])
def test_the_browser_never_waits_forever_without_saying_why(data, want):
    """V2-877 #10: the browser card said «opening the tab…» forever — the main tab's capture was never drawn
    (`shot.png` at `rev`) and every card without one showed the loader, whatever its state."""
    with phone("navegador") as pg:
        pg.evaluate("(d) => window.__render(d)", data)
        pg.wait_for_timeout(100)
        assert want in pg.inner_text(".hb-navt-view"), pg.inner_text(".hb-navt-view")


def test_the_main_tab_draws_its_own_capture():
    with phone("navegador") as pg:
        pg.evaluate("window.__render({mode: 'page', url: 'https://a.example', rev: 3})")
        pg.wait_for_timeout(100)
        assert "shot.png?v=3" in (pg.get_attribute(".hb-navt-img", "src") or "")

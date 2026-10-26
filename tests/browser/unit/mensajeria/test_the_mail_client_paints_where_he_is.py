"""The messaging card says WHERE he is, and its mail section paints like a mail client (RENDERED).

The operator, 2026-10-26, on a screenshot of the home with an email draft above his messages: «no sé si estoy en la
home o en alguno de los apartados». So: a house at the left of the title, lit with the title on the home and dim
inside a section, whose name follows as the current crumb; the home holds only the messages addressed to him (a held
draft lives in its own channel); the mail section opens on the Inbox with every folder one tap away; a draft opens
over the whole card with recipient, subject, text and Send · Save · Discard, and a way back to its folder.

Rendered in a real browser from the real widget module, with the actions recorded — the claims are about what is
painted and what each button asks the server for.
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

_HOST = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;padding:20px;font-family:-apple-system,system-ui,sans-serif}
  .hb-win{position:relative;background:#fff;border:1px solid #e3e8f0;border-radius:16px;
          padding:30px 16px 16px;overflow:hidden;display:flex;flex-direction:column;
          width:760px;height:620px;box-sizing:border-box}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
</style></head><body>
  <div class="hb-win"><div class="hb-scroll"><div id="w"></div></div></div>
</body></html>"""

_KEY = "to:email:hospitality@example.com"
_DRAFT = {"key": _KEY, "text": "Hola,\n\nQueremos integrarnos con vuestra API.", "at": 1700000000, "files": [],
          "target": {"platform": "email", "to": "hospitality@example.com", "name": "hospitality@example.com",
                     "new": True, "subject": "API access"}}
_WA_DRAFT = {"key": "to:whatsapp:rowan pike", "text": "See you at 4", "at": 1700000100, "files": [],
             "target": {"platform": "whatsapp", "to": "+34600111222", "name": "Rowan Pike", "new": True}}
_FOLDERS = [{"name": "INBOX", "role": "inbox", "label": "INBOX"},
            {"name": "[Gmail]/Borradores", "role": "drafts", "label": "Borradores"},
            {"name": "[Gmail]/Enviados", "role": "sent", "label": "Enviados"},
            {"name": "Facturas", "role": "", "label": "Facturas"}]
_ROWS = [{"uid": "905", "from": "a@x.com", "fromName": "Anna", "subject": "Reunión del jueves", "ts": 1700000000,
          "seen": False, "pending": True},
         {"uid": "904", "from": "b@x.com", "fromName": "Stripe", "subject": "Your invoice", "ts": 1699990000,
          "seen": True}]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
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
            page = browser.new_page(viewport={"width": 900, "height": 760})
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/mensajeria/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _data(**extra):
    d = {"platforms": {p: {"status": "connected"} for p in ("whatsapp", "telegram", "email")},
         "items": [{"n": 1, "platform": "whatsapp", "chatId": "a", "from": "Luis", "body": "hola", "highlight": True},
                   {"n": 2, "platform": "telegram", "chatId": "g", "from": "Grupo", "body": "x", "highlight": False}],
         "chats": [{"n": 1, "platform": "whatsapp", "chatId": "a", "name": "Luis", "count": 1, "highlight": True,
                    "last": "hola"}],
         "active_chat": None, "active_items": [], "muted_channels": [], "draft": None,
         "drafts": {_KEY: _DRAFT, _WA_DRAFT["key"]: _WA_DRAFT}, "sent": [], "email_signature": [],
         "mailbox": {"folders": _FOLDERS, "folder": "INBOX", "role": "inbox", "rows": _ROWS, "loading": False,
                     "asked": True, "more": True, "error": "", "open": None, "draft": None}}
    d.update(extra)
    return d


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content(_HOST)
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]);
                                                            return Promise.resolve(null); },
                              top: () => {}, openConnector: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data],
    )


def _calls(page, name):
    return [c[1] for c in page.evaluate("window.__calls") if c[0] == name]


def test_the_home_lights_the_house_and_the_title_and_holds_no_draft(_page):
    _mount(_page, _data())
    assert _page.locator(".hd .homebtn.on").count() == 1
    assert _page.locator(".hd .hdtitle.on").count() == 1
    assert _page.locator(".hd .hdsec").count() == 0
    assert _page.locator(".pending").count() == 0, "a held draft is not a message addressed to him"
    assert _page.get_by_text("API access").count() == 0
    assert "1 para ti" in _page.locator(".hd .sub").inner_text(), "the count is what the home shows"


def test_inside_a_section_the_house_dims_and_the_section_is_the_current_crumb(_page):
    _mount(_page, _data())
    _page.locator(".dots .picon.on").nth(0).click()                      # WhatsApp
    assert _page.locator(".hd .homebtn.on").count() == 0
    assert _page.locator(".hd .hdtitle.on").count() == 0
    assert _page.locator(".hd .hdsec").inner_text() == "WhatsApp"
    assert "See you at 4" in _page.locator(".pending").inner_text(), "its own held draft lives in its channel"
    _page.locator(".hd .homebtn").click()
    assert _page.locator(".hd .homebtn.on").count() == 1
    assert _calls(_page, "show_view")[-1] == {"platform": "all"}


def test_the_mail_section_opens_on_the_inbox_with_every_folder_one_tap_away(_page):
    _mount(_page, _data())
    _page.locator(".dots .picon.on").nth(2).click()                      # email
    assert _page.locator(".hd .hdsec").inner_text() == "Correo"
    entries = _page.locator(".mrail .mnav .mnl").all_inner_texts()
    assert entries == ["Recibidos", "Borradores", "Enviados", "Facturas"]
    assert _page.locator(".mnav.on .mnl").inner_text() == "Recibidos"
    assert "1" in _page.locator(".mnav", has_text="Borradores").inner_text(), "the drafts waiting are counted"
    assert _page.locator(".mlist .mrow").count() == 2
    assert _page.locator(".mrow.unseen").count() == 1 and _page.locator(".mtag").count() == 1
    _page.get_by_text("Your invoice").click()
    assert _calls(_page, "mail_open")[-1] == {"uid": "904", "folder": "INBOX"}
    _page.locator(".mnav", has_text="Enviados").click()
    assert _calls(_page, "mail_folder")[-1] == {"folder": "[Gmail]/Enviados"}


def test_the_drafts_folder_lists_his_drafts_and_one_opens_with_a_tap(_page):
    mb = dict(_data()["mailbox"], folder="[Gmail]/Borradores", role="drafts", rows=[])
    _mount(_page, _data(mailbox=mb, view={"platform": "email", "n": 1, "at": time.time()}))
    row = _page.locator(".mdraftrow")
    assert row.count() == 1 and "hospitality@example.com" in row.inner_text() and "API access" in row.inner_text()
    row.click()
    assert _calls(_page, "open_draft")[-1] == {"key": _KEY}


def test_an_open_draft_takes_the_whole_card_with_everything_to_finish_it(_page):
    mb = dict(_data()["mailbox"], folder="[Gmail]/Borradores", role="drafts", draft=_KEY)
    _mount(_page, _data(mailbox=mb, view={"platform": "email", "n": 2, "at": time.time()}))
    assert _page.locator(".hb-msg.full .mdraft").count() == 1
    assert _page.locator(".hd").count() == 0, "the dashboard header is not stacked over it"
    ins = _page.locator(".mdin")
    assert ins.nth(0).input_value() == "hospitality@example.com" and ins.nth(1).input_value() == "API access"
    assert "integrarnos" in _page.locator(".mdbody").input_value()
    assert _page.locator(".mcrumb").inner_text().replace("\n", " ").count("Borradores") >= 1
    buttons = [b.strip() for b in _page.locator(".dfoot .bt").all_inner_texts()]
    assert buttons == ["Enviar", "Guardar borrador", "Descartar"]
    # The text box takes the card's spare height; the buttons sit at the bottom edge.
    card, foot = _page.locator(".hb-win").bounding_box(), _page.locator(".dfoot").bounding_box()
    assert (card["y"] + card["height"]) - (foot["y"] + foot["height"]) < 40, (card, foot)
    _page.locator(".mdbody").fill("Hello,\n\nAPI access please.")
    _page.get_by_role("button", name="Enviar").click()
    _page.wait_for_timeout(80)
    # ONE order: what is on screen is written into THIS draft and sent — never «the newest draft».
    sent = _calls(_page, "compose")[-1]
    assert sent["key"] == _KEY and sent["send"] is True and sent["text"] == "Hello,\n\nAPI access please.", sent
    assert "Enviando" in _page.locator(".mdnote").inner_text()


def test_the_outcome_of_a_send_comes_back_through_the_state(_page):
    """Taps on this card are queued and answered with nothing: the screen reads `mailbox.note`."""
    mb = dict(_data()["mailbox"], folder="[Gmail]/Borradores", role="drafts", draft=_KEY,
              note={"key": "not_sent", "text": "no tengo a nadie que se llame así", "at": time.time()})
    _mount(_page, _data(mailbox=mb, view={"platform": "email", "n": 4, "at": time.time()}))
    assert _page.locator(".mdnote").inner_text() == "No se ha enviado: no tengo a nadie que se llame así"
    mb = dict(mb, draft=None, note={"key": "sent", "text": "", "at": time.time()})
    _mount(_page, _data(mailbox=mb, view={"platform": "email", "n": 5, "at": time.time()}))
    assert "Enviado" in _page.locator(".mclient .mnote").inner_text()


def test_compose_writes_a_new_mail_and_keeps_his_text_while_the_order_travels(_page):
    _mount(_page, _data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.locator(".mcompose").click()
    ins = _page.locator(".mdin")
    ins.nth(0).fill("partners@example.com")
    ins.nth(1).fill("Hola")
    _page.locator(".mdbody").fill("Texto")
    _page.get_by_role("button", name="Guardar borrador").click()
    assert _calls(_page, "compose")[-1] == {"channel": "email", "text": "Texto", "to": "partners@example.com",
                                             "subject": "Hola"}
    assert _page.locator(".mdbody").input_value() == "Texto"


def test_discard_and_back_are_one_tap_each(_page):
    mb = dict(_data()["mailbox"], folder="[Gmail]/Borradores", role="drafts", draft=_KEY)
    _mount(_page, _data(mailbox=mb, view={"platform": "email", "n": 3, "at": time.time()}))
    _page.get_by_role("button", name="Descartar").click()
    assert _calls(_page, "discard_draft")[-1] == {"key": _KEY}
    _page.locator(".mcrumb .back").click()
    assert _calls(_page, "mail_back")

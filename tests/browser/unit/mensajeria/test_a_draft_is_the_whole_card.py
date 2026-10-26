"""A draft is the whole card: entered from a list, left back to that list, and never painted over one (V2-807 T-02).

The operator, 2026-10-26: «el borrador ocupa el widget entero como contenido único, no lo mezcles con listas de
mensajes… entramos en borrador y de ahí puedo volver a la lista». In his session `open_draft` ran while the card was
closed, the card mounted a second later — and he got the home with the draft's body painted in a strip above the
inbox: one draft, two faces.

The class: a screen chosen by an action is STATE. It survives the card mounting after the order, and an order that
only names the SECTION («enséñame el correo») does not close the draft he is working on. A draft has ONE face — its
own screen; on any list it is a one-line pointer that opens it, never its body and never a Send button. «Back» goes
to the list it was opened from.

Data ops below the screen, then the card RENDERED from a fresh module (what a card mounting after the order sees) at
three widths and on the dark palette.
"""
from __future__ import annotations

import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, mailbox


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    yield


_CATS = [{"key": "primary", "unread": 14}, {"key": "promotions", "unread": 9}]


def _held():
    return data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access",
                                       "text": "Hola,\n\nQueremos integrarnos con vuestra API."})["key"]


def _with_categories():
    db = data.load_db()
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "before": None, "rows": [], "complete": True,
                      "categories": _CATS})
    data.store.save(data.WIDGET_ID, db)


# ── the state ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_draft_opened_with_the_card_closed_is_on_screen_when_the_card_mounts():
    key = _held()
    out = data.apply_action("open_draft", {})
    assert out["ok"] and out["mailbox"]["draft"] == key and out["view"]["platform"] == "email"
    mounted = data.view_data()                         # what the card reads when it mounts a second later
    assert mounted["mailbox"]["draft"] == key and key in mounted["drafts"]


def test_an_order_that_only_names_the_section_keeps_the_draft_he_is_working_on():
    key = _held()
    data.apply_action("open_draft", {"key": key})
    out = data.apply_action("show_view", {"platform": "email"})
    assert out["mailbox"]["draft"] == key, "«enséñame el correo» lands on the draft, it does not close it"
    out = data.apply_action("mail_folder", {"folder": "sent"})
    assert out["mailbox"]["draft"] is None, "naming a list leaves the draft — he chose another screen"


def test_an_open_message_still_goes_back_to_its_list_when_the_section_is_entered():
    db = data.load_db()
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "before": None, "rows": [{"uid": "4"}]})
    data.store.save(data.WIDGET_ID, db)
    data.apply_action("mail_open", {"uid": "4"})
    assert data.apply_action("show_view", {"platform": "email"})["mailbox"]["open"] is None


def test_back_from_a_draft_returns_to_the_list_it_was_opened_from():
    _with_categories()
    key = _held()
    data.apply_action("mail_folder", {"folder": "inbox", "category": "promotions"})
    out = data.apply_action("open_draft", {"key": key})
    assert out["mailbox"]["role"] == "drafts" and out["mailbox"]["back_to"] == {"folder": "INBOX",
                                                                               "category": "promotions"}
    out = data.apply_action("mail_back", {})
    assert out["mailbox"]["draft"] is None
    assert (out["mailbox"]["folder"], out["mailbox"]["category"]) == ("INBOX", "promotions")
    # Opened from the Drafts entry, it goes back to Drafts.
    data.apply_action("mail_folder", {"folder": "drafts"})
    data.apply_action("open_draft", {"key": key})
    out = data.apply_action("mail_back", {})
    assert out["mailbox"]["role"] == "drafts" and out["mailbox"]["draft"] is None


def test_discard_and_send_also_return_to_the_list_it_came_from():
    _with_categories()
    key = _held()
    data.apply_action("mail_folder", {"folder": "inbox"})
    data.apply_action("open_draft", {"key": key})
    out = data.apply_action("discard_draft", {"key": key})
    assert (out["mailbox"]["folder"], out["mailbox"]["category"]) == ("INBOX", "primary")
    key = _held()
    data.apply_action("open_draft", {"key": key})
    out = data.apply_action("compose", {"key": key, "text": "Edited", "send": True})
    assert out["ok"] and out["mailbox"]["draft"] is None and out["mailbox"]["folder"] == "INBOX"


# ── RENDERED ──────────────────────────────────────────────────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api")
from tests.browser.unit.mensajeria import test_the_mail_rail_paints_at_every_width as rail  # noqa: E402

_page = rail._page
_KEY = "to:email:hospitality@example.com"
_DRAFT = {"key": _KEY, "text": "Hola,\n\nQueremos integrarnos con vuestra API.", "at": 1700000000, "files": [],
          "target": {"platform": "email", "to": "hospitality@example.com", "name": "hospitality@example.com",
                     "new": True, "subject": "API access"}}


def _draft_data(**mb):
    d = rail._data(folder="[Gmail]/Drafts", role="drafts", category=None, draft=_KEY,
                   back_to={"folder": "INBOX", "category": "promotions"}, **mb)
    d["drafts"] = {_KEY: _DRAFT}
    return d


@pytest.mark.parametrize("w", [760, 560, 380])
def test_the_draft_is_the_cards_only_content_at_every_width(_page, w):
    rail._mount(_page, _draft_data(), w=w)
    assert _page.locator(".hb-msg.full .mdraft").count() == 1
    for gone in (".mrail", ".mlist", ".mrow", ".hd", ".pending", ".mdptr", ".mdrawerbtn"):
        assert _page.locator(gone).count() == 0, f"{gone} painted beside the draft"
    assert _page.locator(".mdbody").input_value().startswith("Hola,")
    assert [b.strip() for b in _page.locator(".dfoot .bt").all_inner_texts()] == ["Enviar", "Guardar borrador",
                                                                                 "Descartar"]
    card, foot = _page.locator(".hb-win").bounding_box(), _page.locator(".dfoot").bounding_box()
    assert foot["y"] + foot["height"] <= card["y"] + card["height"] + 1, "the buttons are inside the card"
    sw = _page.evaluate("() => { const p = document.querySelector('.hb-scroll'); return p.scrollWidth - p.clientWidth; }")
    assert sw <= 0


def test_back_names_and_reaches_the_list_the_draft_came_from(_page):
    rail._mount(_page, _draft_data())
    back = _page.locator(".mcrumb .back")
    assert back.inner_text() == "← Promociones"
    back.click()
    assert rail._calls(_page, "mail_back") == [{}]


def test_on_a_list_a_held_draft_is_one_line_that_opens_it_never_its_body(_page):
    d = rail._data()
    d["drafts"] = {_KEY: _DRAFT}
    rail._mount(_page, d)
    ptr = _page.locator(".mdptr")
    assert ptr.count() == 1 and "hospitality@example.com" in ptr.inner_text()
    assert "integrarnos" not in _page.locator(".mpanel").inner_text(), "the body is the draft screen's, only"
    assert _page.get_by_role("button", name="Enviar").count() == 0
    ptr.click()
    assert rail._calls(_page, "open_draft")[-1] == {"key": _KEY}


def test_the_draft_reads_on_the_dark_palette(_page):
    rail._mount(_page, _draft_data())
    assert rail._contrast(_page, ".mdbody", ".hb-win") >= 7
    assert rail._contrast(_page, ".mdk", ".hb-win") >= 4.5

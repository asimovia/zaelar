"""His mail categories are criteria he reorganises by voice, stored as rows of the rules table (V2-807 T-03).

The operator, 2026-10-26: «la gente por voz se organice los criterios de clasificación como quiera; tú déjalos por
defecto tal y como van en Gmail». The default is the provider's own sorting — no row, nothing applied. What he says
on top of it («los de Amazon que vayan a Principal», «no me enseñes Social») is a row at `widget:mensajeria`, scoped
to the mail card, listed and removable like every rule, and read by CODE on every page ask: a route is composed into
the provider's own query, so the list and its count follow it, and nothing moves in his real mailbox.

The sentence → row step is the turn model's verdict over what is declared (the live cases `msg-*-mail-*` in
`tests/brain/cases/messaging-live.json`, ES+EN); here the payload it produces is applied end to end: stored, read
back after a «restart», applied through the connector against a recorded Gmail session, shown, and removed.
"""
from __future__ import annotations

import pytest

import rules
from connectors.email import folders
from widgets import store as wstore
from widgets.mensajeria import data, mail_rules, mailbox

from tests.browser.unit.mensajeria.test_the_inbox_is_sorted_the_way_the_provider_sorts_it import _Gmail, _Mb


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    rules._reset_for_tests()
    db = data.load_db()
    mailbox.fold(db, {"platform": "email", "folder": "INBOX", "before": None, "rows": [], "complete": True,
                      "categories": [{"key": "primary", "unread": 1}, {"key": "social", "unread": 0},
                                     {"key": "promotions", "unread": 4}]})
    mailbox.go(db, "inbox")
    db["pending_mail"] = []
    data.store.save(data.WIDGET_ID, db)
    yield
    rules._reset_for_tests()


def _mine():
    return [r for r in rules.all_rows(include_defaults=False) if r["scope"] == "widget:mensajeria"]


@pytest.mark.parametrize("said", ["Los correos de Amazon que vayan a Principal",
                                  "Put the emails from amazon.com in Primary"])
def test_a_spoken_route_is_a_row_of_his_rules_and_the_provider_lists_by_it(said):
    out = data.apply_action("mail_sort", {"from": "amazon.com", "to": "primary", "said": said})
    assert out["ok"] and out["result"]["rule"] == said
    [row] = _mine()
    assert (row["kind"], row["key"], row["value"], row["text"], row["source"]) == \
        ("pref", "mail_route:amazon.com", "primary", said, "user")
    # Applied by code: the page asked for Primary carries his route…
    order = data.load_db()["pending_mail"][-1]
    assert order["category"] == "primary" and order["routes"] == [{"from": "amazon.com", "to": "primary"}]
    # …and the provider's own query brings Amazon's mail into Primary and its count with it.
    page = folders.list_page(_Mb(_Gmail()), "INBOX", None, 30, category="primary", routes=order["routes"])
    assert "104" in [r["uid"] for r in page["rows"]]
    assert {c["key"]: c["unread"] for c in page["categories"]} == {
        "primary": 2, "social": 0, "promotions": 3, "updates": 1, "forums": 0}
    promos = folders.list_page(_Mb(_Gmail()), "INBOX", None, 30, category="promotions", routes=order["routes"])
    assert "104" not in [r["uid"] for r in promos["rows"]], "it left Promotions on the card, not in his mailbox"


def test_it_survives_a_restart_and_a_second_route_for_the_same_sender_replaces_the_first():
    data.apply_action("mail_sort", {"from": "Amazon.com", "to": "primary"})
    from rules import store as _rstore
    _rstore._conns.clear()                 # a fresh process: nothing but the database file
    _rstore._invalidate()
    assert mail_rules.routes() == [{"from": "amazon.com", "to": "primary"}]
    data.apply_action("mail_sort", {"from": "amazon.com", "to": "social"})
    assert mail_rules.routes() == [{"from": "amazon.com", "to": "social"}] and len(_mine()) == 1


def test_hiding_a_category_takes_it_off_the_rail_and_showing_it_brings_it_back():
    data.apply_action("mail_folder", {"folder": "inbox", "category": "social"})
    out = data.apply_action("mail_sort", {"hide": "social", "said": "No me enseñes Social"})
    assert [c["key"] for c in out["mailbox"]["categories"]] == ["primary", "promotions"]
    assert out["mailbox"]["category"] == "primary", "the list he was on is gone: the first visible one"
    assert data.apply_action("mail_folder", {"folder": "social"})["mailbox"]["category"] == "primary"
    out = data.apply_action("mail_sort", {"show": "social"})
    assert [c["key"] for c in out["mailbox"]["categories"]] == ["primary", "social", "promotions"]
    assert _mine() == []


def test_it_is_visible_in_his_words_and_removable_by_voice_or_in_the_card():
    data.apply_action("mail_sort", {"from": "amazon.com", "to": "primary", "said": "Amazon a Principal"})
    data.apply_action("mail_sort", {"hide": "social"})
    listing = data.view_data()["mailbox"]["rules"]
    assert [r["text"] for r in listing] == ["Amazon a Principal", "Don't show Social"]
    out = data.apply_action("mail_sort", {"forget": "amazon.com"})              # by voice: the sender
    assert out["ok"] and mail_rules.routes() == []
    out = data.apply_action("mail_sort", {"forget": listing[1]["id"]})         # in the card: the row's ✕
    assert out["ok"] and mail_rules.hidden() == set() and _mine() == []
    assert data.apply_action("mail_sort", {"forget": "nobody.example"})["ok"] is False


def test_what_the_provider_never_returned_is_refused_and_nothing_moves_in_his_mailbox():
    out = data.apply_action("mail_sort", {"from": "amazon.com", "to": "travel"})
    assert out["ok"] is False and out["error"] == "unknown_category" and _mine() == []
    out = data.apply_action("mail_sort", {"from": 'amazon" OR in:anywhere', "to": "primary"})
    assert out["ok"] is False and out["error"] == "no_sender", "a sender can never carry search syntax"
    data.apply_action("mail_sort", {"from": "amazon.com", "to": "primary"})
    db = data.load_db()
    for q in ("pending_archive", "pending_trash", "pending_send", "pending_reply", "pending_read"):
        assert not db.get(q), f"{q}: a criterion never touches the real mailbox"
    assert all(set(o) <= {"platform", "folder", "before", "limit", "category", "routes"}
               for o in db.get("pending_mail") or []), "only pages are asked"


def test_a_mailbox_without_categories_has_no_criteria_to_reorganise():
    db = data.load_db()
    db["mailbox"]["categories"] = []
    data.store.save(data.WIDGET_ID, db)
    out = data.apply_action("mail_sort", {"from": "amazon.com", "to": "primary"})
    assert out["ok"] is False and out["error"] == "no_categories"


def test_the_action_is_declared_for_the_model_with_every_field_it_reads():
    import json
    import pathlib
    man = json.loads((pathlib.Path(data.__file__).parent / "manifest.json").read_text())
    spec = man["actions"]["mail_sort"]
    assert set(spec["payload"]) == {"from", "to", "hide", "show", "forget", "said"}
    assert "mail_sort" in data.ACTIONS and not spec.get("confirm")


# ── RENDERED: his criteria are in the rail, each with its ✕ ─────────────────────────────────────────────────────

pytest.importorskip("playwright.sync_api")
from tests.browser.unit.mensajeria import test_the_mail_rail_paints_at_every_width as rail  # noqa: E402

_page = rail._page


def test_the_rail_lists_his_criteria_and_each_one_is_removed_with_a_tap(_page):
    d = rail._data(rules=[{"id": "r_amz", "text": "Amazon a Principal"}, {"id": "r_soc", "text": "No enseñar Social"}])
    rail._mount(_page, d)
    assert _page.locator(".mrules .mruleshd").inner_text().strip().lower() == "tus criterios"
    assert _page.locator(".mrules .mrulet").all_inner_texts() == ["Amazon a Principal", "No enseñar Social"]
    _page.locator(".mrule", has_text="Amazon").locator(".mrulex").click()
    assert rail._calls(_page, "mail_sort")[-1] == {"forget": "r_amz"}
    rail._mount(_page, rail._data(rules=[]))
    assert _page.locator(".mrules").count() == 0, "no criteria of his: the provider's sorting, nothing to show"

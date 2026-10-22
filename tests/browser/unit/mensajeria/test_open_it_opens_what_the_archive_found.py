"""«Open it» after an archive search opens the mail it FOUND (node 4.237).

Demo pass 62, E2 (2026-09-29): «did acme send me something?» found the receipt in the archive. Its
conversation was on the card — a thread brought back by an earlier «load previous», with no name — but not in the
inbox list, whose only row was an HostCo mail. «Open it» came back as «there's nothing to open», and the repair
pass then opened the ONE chat the list showed: the wrong mail. The card now remembers what the archive last found,
a bare `open` opens that, and its digest says so to the model.
"""
import time

import pytest

ACME = "invoice+statements@acme-cloud.example"
ROW = {"id": "3335", "platform": "email", "chat_id": ACME, "chat_name": "", "sender": "Acme Cloud",
       "direction": "in", "ts": time.time() - 3600, "body": "[Asunto: Your receipt from Acme Cloud #1000-0001]\nAcme Cloud",
       "msg_id": "100001"}


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data, views
    monkeypatch.setattr(views, "archive_rows", lambda payload: [ROW] if "acme" in str(payload).lower() else [])
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "chatId": "support@hosting.example", "name": "Soporte de HostCo",
                    "text": "[Asunto: Mantenimiento programado]", "ts": time.time() - 60, "messageId": "m-host"}]
    db["threads"] = {"email|support@hosting.example": {"name": "Soporte de HostCo", "msgs": [
                         {"id": "m-host", "dir": "in", "who": "Soporte de HostCo", "body": "Mantenimiento", "ts": time.time() - 60}]},
                     f"email|{ACME}": {"name": "", "msgs": [
                         {"id": "100001", "dir": "in", "who": "", "body": "Your receipt", "ts": ROW["ts"]}]}}
    data.store.save(data.WIDGET_ID, db)
    return data


def test_a_bare_open_after_the_search_opens_the_found_mail_not_the_inbox_row(md):
    md.apply_action("search_archive", {"query": "acme"})
    md.apply_action("open", {})
    assert md.load_db()["active_chat"] == {"platform": "email", "chatId": ACME}


def test_the_digest_tells_the_model_the_found_mail_is_on_the_card(md):
    md.apply_action("search_archive", {"query": "acme"})
    from widgets.mensajeria import inbox_read
    digest = inbox_read.prompt_digest()
    assert "LO ÚLTIMO QUE ENCONTRASTE EN EL ARCHIVO" in digest and "Your receipt from Acme Cloud #1000-0001" in digest
    assert "`open` sin nada" in digest


def test_a_named_open_still_wins_and_a_stale_find_opens_nothing(md, monkeypatch):
    md.apply_action("search_archive", {"query": "acme"})
    md.apply_action("open", {"name": "HostCo"})
    assert md.load_db()["active_chat"]["chatId"] == "support@hosting.example"
    db = md.load_db()
    db["active_chat"] = None
    db["last_found"]["at"] = time.time() - md.FOUND_TTL_S - 5
    md.store.save(md.WIDGET_ID, db)
    md.apply_action("open", {})
    assert not md.load_db().get("active_chat")
    assert md.last_found(md.load_db()) is None


def test_a_search_that_found_nothing_remembers_nothing(md):
    md.apply_action("search_archive", {"query": "nobody"})
    assert md.last_found(md.load_db()) is None


def test_a_name_that_shares_a_word_with_the_found_mail_opens_it(md):
    """Demo pass 66, E2: open {name: "Acme invoice"} missed the thread named by its address."""
    md.apply_action("search_archive", {"query": "acme"})
    md.apply_action("open", {"name": "Acme invoice"})
    assert md.load_db()["active_chat"] == {"platform": "email", "chatId": ACME}

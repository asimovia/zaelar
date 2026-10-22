"""A sender the inbox never mentions is asked of the archive, even when other words match (demo pass 59, E1).

«Did Acme send me something?» reached the card as «¿Hay algún email de Acme? … remitente, asunto, fecha».
Every email body starts with «[Asunto: …]», so the inbox matched four unrelated mails, the archive was asked only
when the inbox matched NOTHING, and the answer was «nothing from Acme» with the receipt in the archive."""
import time

import pytest


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data
    db = data.load_db()
    db["items"] = [{"platform": "email", "from": "Samuel", "body": "[Asunto: RE: contrato] Bon dia Alex", "ts": time.time()}]
    data.store.save(data.WIDGET_ID, db)
    return data


def _asked(monkeypatch):
    calls = []
    from widgets.mensajeria import views
    monkeypatch.setattr(views, "read_query_answer", lambda q: calls.append(q) or "Del ARCHIVO: Acme invoice")
    from widgets import directory
    monkeypatch.setattr(directory, "reachable", lambda q: "")
    return calls


def test_a_sender_absent_from_the_inbox_goes_to_the_archive(md, monkeypatch):
    from widgets.mensajeria import inbox_read
    calls = _asked(monkeypatch)
    out = inbox_read.read_query("¿Hay algún email de Acme (acme-cloud.example) en la bandeja? remitente, asunto, fecha")
    assert calls, "the archive was never asked"
    assert "Acme invoice" in out


def test_a_question_the_inbox_answers_whole_stays_in_the_inbox(md, monkeypatch):
    from widgets.mensajeria import inbox_read
    calls = _asked(monkeypatch)
    out = inbox_read.read_query("what did Samuel say?")
    assert "Samuel" in out and not calls

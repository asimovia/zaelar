"""The card's answering veto and its `open` action resolve a conversation through ONE resolver.

Live demo pass on b136, E2: «did <sender> send me something?» found the mail in the archive (the card remembered it
as `last_found`), then «open it» came as `open {name: "<sender display name>"}`. The ACTION would have opened the
found mail — a name sharing a word with what the card last found means that mail — but the backed route runs the
card's read-only veto (`answers._open`) BEFORE queueing the order, and the veto resolved names without the card's
last find: «no encuentro ese chat», nothing queued, nothing opened. Under it, the found mail's thread existed but
was EMPTY (a «load previous» that came back with nothing), the bring-back counted the bare thread key as holding the
mail and never asked it again, and an open would have auto-closed on nothing — then E3's forward found no mail on the
card. Tested through the real door (`server_api._answer_backed`), ES and EN, invented people.
"""
import time

import pytest

EN_ADDR = "billing+notices@lumenfield-studio.example"
ES_ADDR = "facturas@ferreteria-olmedo.example"


def _row(addr, sender, subject, uid):
    return {"id": uid, "platform": "email", "chat_id": addr, "chat_name": "", "sender": sender,
            "direction": "in", "ts": time.time() - 3600, "body": f"[Asunto: {subject}]\n{sender}", "msg_id": uid}


ROWS = {
    "lumenfield": _row(EN_ADDR, "Lumenfield Studio", "Your receipt #4471", "200001"),
    "olmedo": _row(ES_ADDR, "Ferretería Olmedo", "Tu factura de noviembre", "200002"),
}


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data, views
    monkeypatch.setattr(views, "archive_rows",
                        lambda payload: [r for k, r in ROWS.items() if k in str(payload).lower()])
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "chatId": "news@weekly-digest.example", "name": "Weekly Digest",
                    "text": "[Asunto: This week]", "ts": time.time() - 60, "messageId": "m-news"}]
    # The found mails' threads exist (brought back by «load previous») but carry no name: named by an address.
    db["threads"] = {f"email|{addr}": {"name": "", "msgs": []} for addr in (EN_ADDR, ES_ADDR)}
    data.store.save(data.WIDGET_ID, db)
    return data


def _veto(payload):
    from widgets import server_api
    return server_api._answer_backed("mensajeria", "open", payload)


@pytest.mark.parametrize("query,said,addr", [
    ("lumenfield", "Lumenfield Studio", EN_ADDR),
    ("olmedo", "Ferretería Olmedo", ES_ADDR),
])
def test_the_veto_lets_through_the_found_mail_the_action_opens(md, query, said, addr):
    md.apply_action("search_archive", {"query": query})
    ans = _veto({"name": said})
    assert not (isinstance(ans, dict) and ans.get("ok") is False), ans
    md.apply_action("open", {"name": said})
    db = md.load_db()
    assert db["active_chat"] == {"platform": "email", "chatId": addr}      # kept open while the mail arrives
    uid = next(r["msg_id"] for r in ROWS.values() if r["chat_id"] == addr)
    assert any(o.get("chatId") == addr and o.get("beforeId") == str(int(uid) + 1)
               for o in db.get("pending_history") or [])


def test_an_empty_thread_does_not_hold_the_found_mail(md):
    md.apply_action("search_archive", {"query": "lumenfield"})
    asked = [o for o in md.load_db().get("pending_history") or [] if o.get("chatId") == EN_ADDR]
    assert asked and asked[0]["beforeId"] == "200002"


def test_a_mail_the_card_holds_is_not_asked_back(md):
    db = md.load_db()
    db["threads"][f"email|{EN_ADDR}"]["msgs"] = [{"id": "200001", "dir": "in", "who": "", "body": "Your receipt",
                                                  "ts": time.time() - 3600}]
    md.store.save(md.WIDGET_ID, db)
    md.apply_action("search_archive", {"query": "lumenfield"})
    md.apply_action("open", {"name": "Lumenfield Studio"})
    db = md.load_db()
    assert db["active_chat"] == {"platform": "email", "chatId": EN_ADDR}
    assert not [o for o in db.get("pending_history") or [] if o.get("chatId") == EN_ADDR]


def test_a_name_nothing_on_the_card_carries_is_still_vetoed(md):
    md.apply_action("search_archive", {"query": "lumenfield"})
    ans = _veto({"name": "Quillan Baptiste"})
    assert isinstance(ans, dict) and ans.get("ok") is False
    assert "Quillan" not in str(md.load_db().get("active_chat"))


def test_without_a_fresh_find_the_veto_and_the_action_refuse_alike(md):
    md.apply_action("search_archive", {"query": "olmedo"})
    db = md.load_db()
    db["last_found"]["at"] = time.time() - md.FOUND_TTL_S - 5
    md.store.save(md.WIDGET_ID, db)
    assert _veto({"name": "Ferretería Olmedo"}).get("ok") is False
    assert md.apply_action("open", {"name": "Ferretería Olmedo"}).get("ok") is False

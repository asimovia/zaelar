"""The messaging card does what the native apps do: attach photos, videos, voice notes and documents on every
platform, and create a group.

Until now a file could only leave by email («Solo sé enviar adjuntos por correo») and nothing could create a
group. Files reach a send three ways — picked in the card (an upload, named in `files`), forwarded from a message
that arrived (`attach_from`), or both — and travel through the same queues as text. A name in an action can
only ever point inside the widget's own data dir: a send is the one thing that takes a file OFF this machine.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    for name, platform, handle in (("Ana Torres", "whatsapp", "+34600111222"), ("Luis Gil", "whatsapp", "+34600333444"),
                                   ("Iván Petrenko", "telegram", "@ivanm")):
        cd.apply_action("add_contact", {"name": name})
        cid = next(c["id"] for c in cd.load_db()["contacts"] if c["name"] == name)
        cd.apply_action("set_channel", {"contactId": cid, "platform": platform, "handle": handle})
    return md


def _upload(name="up_abc123_foto.jpg"):
    from widgets import store
    path = os.path.join(store.data_dir("mensajeria"), name)
    with open(path, "wb") as f:
        f.write(b"\xff\xd8jpeg")
    return name, path


def test_a_photo_picked_in_the_card_goes_by_whatsapp_and_alone_is_a_message(box):
    name, path = _upload()
    r = box.apply_action("send_to", {"contact": "Ana", "channel": "whatsapp", "files": [name]})
    assert r["ok"], r
    order = box.load_db()["pending_send"][0]
    assert order["attachments"] == [path] and order["text"] == ""


def test_a_name_can_never_point_outside_the_widget_dir(box, tmp_path):
    from widgets import store
    from widgets.mensajeria import media
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    folder = store.data_dir("mensajeria")
    open(os.path.join(folder, "state_copy.json"), "w").close()
    assert media.local_paths(folder, [str(outside), "../secret.txt", "state_copy.json", "up_nope.jpg"]) == []


def test_files_ride_in_the_conversations_draft_and_go_with_the_reply(box):
    name, path = _upload()
    db = box.load_db()
    db["threads"] = {"telegram|42": {"name": "Marta", "msgs": [{"id": "42:1", "dir": "in", "who": "Marta",
                                                               "body": "¿me pasas la foto?", "ts": 1}]}}
    db["active_chat"] = {"platform": "telegram", "chatId": "42"}
    box.store.save("mensajeria", db)
    target = {"platform": "telegram", "chatId": "42"}
    assert box.apply_action("draft", {**target, "text": "", "files": [name]})["ok"]
    r = box.apply_action("send_draft", target)
    assert r["ok"] and r["attachments"] == 1
    rep = box.load_db()["pending_reply"][-1]
    assert rep["attachments"] == [path] and rep["chatId"] == "42"


def test_a_group_is_created_with_everyone_resolved_or_not_at_all(box):
    r = box.apply_action("create_group", {"platform": "whatsapp", "name": "Viaje", "members": "Ana y Luis",
                                          "text": "¡Hola a los dos!"})
    assert r["ok"], r
    order = box.load_db()["pending_group"][0]
    assert order["name"] == "Viaje" and [m["name"] for m in order["members"]] == ["Ana Torres", "Luis Gil"]
    assert all(m["to"] for m in order["members"]) and order["text"] == "¡Hola a los dos!"

    bad = box.apply_action("create_group", {"platform": "whatsapp", "name": "Otro", "members": ["Ana", "Nadie"]})
    assert bad["ok"] is False and "Nadie" in bad["error"]
    assert len(box.load_db()["pending_group"]) == 1, "one unknown member and nothing is created"


def test_a_forward_goes_by_the_channel_he_names(box):
    name, path = _upload("img_9f.jpg")
    db = box.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "1", "messageId": "m1", "from": "Ana", "body": "foto",
                    "mediaType": "image", "media": [{"url": "/x", "type": "image", "name": name}]}]
    box.store.save("mensajeria", db)
    r = box.apply_action("forward", {"contact": "Iván", "channel": "telegram", "messageId": "m1"})
    assert r["ok"], r
    order = box.load_db()["pending_send"][-1]
    assert order["platform"] == "telegram" and order["attachments"] == [path]

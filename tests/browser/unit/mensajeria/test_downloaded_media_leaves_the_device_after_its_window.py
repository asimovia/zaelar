"""Downloaded media leaves this device after the operator's window (widgets/mensajeria/media.py).

Every picture, video, voice note and attachment the connectors downloaded was kept forever, flat in the widget's
data dir — measured on a working install: 4,417 files, 5.4 GB, copies of what is still on the phone. The window
is 14 days by default and the operator's choice; past it a file is deleted and the message keeps its text, its
media type and a `mediaGone` mark. Nothing that is not a connector's download is ever touched.
"""
from __future__ import annotations

import os
import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, media


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from nucleo import consent
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path / "ws"))
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


def _file(folder, name, days_old):
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(b"x" * 100)
    t = time.time() - days_old * 86400
    os.utime(path, (t, t))
    return name


def _ref(name, kind="image"):
    return {"url": f"/widgets/mensajeria/asset/{name}", "type": kind, "name": name}


def test_old_downloads_go_new_ones_stay_and_nothing_else_is_touched():
    folder = wstore.data_dir("mensajeria")
    old_img, new_img = _file(folder, "img_old.jpg", 20), _file(folder, "img_new.jpg", 2)
    old_tg, old_mail = _file(folder, "tg_1_2.ogg", 40), _file(folder, "eml_3.pdf", 30)
    _file(folder, "notes_old.txt", 400)                             # not a connector download
    db = data.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "1", "messageId": "a", "mediaType": "image",
                    "media": [_ref(old_img)]}]
    db["threads"] = {"telegram|9": {"msgs": [{"id": "t1", "mediaType": "ptt", "media": [_ref(old_tg, "ptt")]},
                                             {"id": "t2", "mediaType": "image", "media": [_ref(new_img)]}]}}
    res = media.sweep(db, folder)
    assert res["files"] == 3 and res["bytes"] == 300 and res["messages"] == 2
    assert sorted(os.listdir(folder)) == sorted(["img_new.jpg", "notes_old.txt"] +
                                                [n for n in os.listdir(folder) if n.endswith((".json", ".db"))])
    item = db["items"][0]
    assert "media" not in item and item["mediaGone"] and item["mediaType"] == "image", \
        "the message still says what was there"
    t1, t2 = db["threads"]["telegram|9"]["msgs"]
    assert t1["mediaGone"] and "media" not in t1
    assert t2["media"] == [_ref(new_img)] and "mediaGone" not in t2


def test_always_deletes_nothing_but_still_unhooks_a_file_already_missing():
    folder = wstore.data_dir("mensajeria")
    _file(folder, "vid_old.mp4", 365)
    db = {"media_days": 0, "items": [{"media": [_ref("img_vanished.jpg")], "mediaType": "image"}]}
    res = media.sweep(db, folder)
    assert res["files"] == 0 and os.path.isfile(os.path.join(folder, "vid_old.mp4"))
    assert db["items"][0]["mediaGone"], "a broken picture is worse than a label"


def test_the_window_is_the_operators_choice_and_defaults_to_fourteen_days():
    assert data.view_data()["media_days"] == 14
    r = data.apply_action("set_media_days", {"days": 30})
    assert r["ok"] and data.view_data()["media_days"] == 30
    assert data.apply_action("set_media_days", {"days": "siempre"})["result"]["media_days"] == 0
    assert data.apply_action("set_media_days", {"days": 3})["ok"] is False
    assert data.view_data()["media_days"] == 0


def test_the_sweep_runs_once_an_hour_and_a_new_choice_applies_on_the_next_beat():
    db = {}
    assert media.due(db)
    media.sweep(db, wstore.data_dir("mensajeria"))
    assert not media.due(db)
    media.set_days(db, 7)
    assert media.due(db)

"""His recent searches are kept for the bar's empty search field, and a result keeps the length it showed (2026-11-17).

The YouTube app's search page lists what he searched lately; the card's bar does the same from `recent_queries`, which
the `search` action writes — voice and hand alike, since both send that one action. Newest first, eight at most, one
entry per question however it was spelled (the normalisation `search` already uses to tell a repeat). A row of the band
also carries its `duration`, read from the results page (`search/video.py`), for the picture's badge.
"""
import io
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt
from widgets.youtube import actions, helpers

_ROW = ('{{"videoRenderer":{{"videoId":"{id}","title":{{"runs":[{{"text":"{t}"}}]}},'
        '"ownerText":{{"runs":[{{"text":"Canal"}}]}}{x}}}}}')
_HTML = (_ROW.format(id="AAAAAAAAAA1", t="Uno", x=',"lengthText":{"simpleText":"12:45"}')
         + _ROW.format(id="BBBBBBBBBB2", t="Dos", x=""))


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(_HTML.encode("utf-8")))


def _db():
    return yt._load()


def test_a_search_puts_its_question_first_once_and_keeps_eight(sandbox):
    for q in ["paella", "regatas", "lofi"]:
        yt.apply_action("search", {"query": q})
    assert _db()["recent_queries"] == ["lofi", "regatas", "paella"]
    yt.apply_action("search", {"query": "  Paélla "})                 # the same question, spelled otherwise
    assert _db()["recent_queries"] == ["Paélla", "lofi", "regatas"]
    for i in range(10):
        yt.apply_action("search", {"query": f"q{i}"})
    rq = _db()["recent_queries"]
    assert len(rq) == 8 and rq[0] == "q9" and "Paélla" not in rq


def test_an_unanswered_search_is_still_his_recent_question(sandbox, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(b"<html></html>"))
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [])
    out = yt.apply_action("search", {"query": "nada de nada"})
    assert out.get("ok") is False and _db()["recent_queries"] == ["nada de nada"]


def test_a_result_keeps_the_length_its_picture_showed(sandbox):
    yt.apply_action("search", {"query": "uno"})
    band = _db()["search_results"]
    assert [(r["videoId"], r["duration"]) for r in band] == [("AAAAAAAAAA1", "12:45"), ("BBBBBBBBBB2", "")]


def test_the_seed_declares_the_key_and_the_action_owns_the_writer():
    assert helpers._SEED["recent_queries"] == []
    assert callable(actions._remember_query)


def test_a_pasted_wall_of_text_is_kept_as_a_short_question():
    db = {"recent_queries": ["lofi"]}
    actions._remember_query(db, "x" * 500)
    assert len(db["recent_queries"][0]) <= 120 and db["recent_queries"][1] == "lofi"

"""A page player whose candidates are ALL refused stops after `WALK_MAX` and says so, with the site as the fallback.

Live demo pass on b136, U1-U3: «play some madonna» / «no, put like a prayer» — every candidate the lookup found came
back from the IFrame API as 150 (its owner refuses embedding; label-owned music does it as a class). The music card
replaced each refused song with the next one the same words found, ~20 of them in 40 s, nothing sounding, no line
said, and «pause it» then closed the errand as «couldn't finish». Now ONE order walks at most
`availability.WALK_MAX` refusals (shared with the video card), then the card keeps `player_error`, carries the watch
URL as the declared fallback (data, in the brain's digest) and returns a `tell` naming what the ORDER put on — in
his language. A new order starts a new walk. Invented songs and artists.
"""
from __future__ import annotations

import itertools

import pytest

from widgets.musica import data as md
from widgets.youtube import availability as av


@pytest.fixture
def endless(monkeypatch, tmp_path):
    """A lookup that always finds one more candidate — the shape of a song whose every upload refuses embedding."""
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True})
    store.save("musica", {"yt": {"videoId": "ORDERED0001", "title": "Copper Lanterns", "query": "copper lanterns",
                                 "paused": False, "cmd_seq": 3, "volume": 70},
                          "source": {"provider": "youtube", "screen": "desktop:aa11"}})
    ids = (f"CANDIDATE{n:02d}" for n in itertools.count(1))
    monkeypatch.setattr("connectors.music.youtube_resolve._resolve",
                        lambda q, skip=(): (next(ids), f"Copper Lanterns ({q})", "found"))


def _refuse_current():
    vid = md._load_db()["yt"]["videoId"]
    return md.apply_action("player_error", {"code": "150", "videoId": vid})


@pytest.mark.parametrize("lang,said", [("en", "I can open it on YouTube"), ("es", "te la abro en YouTube")])
def test_the_walk_stops_at_its_bound_and_tells_him(endless, monkeypatch, lang, said):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    results = [_refuse_current() for _ in range(av.WALK_MAX)]
    assert all(r.get("swapped_to") for r in results[:-1]), results
    last = results[-1]
    yt = md._load_db()["yt"]
    assert not last.get("swapped_to") and yt["player_error"] == "150", "the walk ends at its bound"
    assert said in last.get("tell", "") and "Copper Lanterns" in last["tell"], last
    assert yt["refused_at"].endswith(yt["videoId"])
    digest = md.prompt_digest()
    assert "REFUSED" in digest and yt["refused_at"] in digest, "the site is offered to the brain as data"


def test_a_swap_inside_the_walk_tells_nothing(endless):
    assert not _refuse_current().get("tell")


def test_a_new_order_starts_a_new_walk(endless):
    for _ in range(av.WALK_MAX - 1):
        _refuse_current()
    db = md._load_db()
    db["yt"].update({"videoId": "NEWORDER001", "title": "Saffron Tide", "query": "saffron tide", "player_error": ""})
    md._persist(db)
    r = _refuse_current()
    assert r.get("swapped_to"), "a fresh order never inherits the previous order's refusals"


def test_the_video_card_walk_is_bounded_alike(monkeypatch):
    """The same bound on the video card: our own pick is replaced at most WALK_MAX - 1 times per order."""
    ids = (f"VIDEOCAND{n:02d}" for n in itertools.count(1))
    monkeypatch.setattr(av, "next_unblocked", lambda db, dead: {"videoId": next(ids), "title": "Driftwood Choir"})
    monkeypatch.setattr(av, "swap_to", lambda db, it: db.update(videoId=it["videoId"], title=it["title"]))
    db = {"videoId": "VIDEOORD001", "title": "Driftwood Choir — live"}
    kinds = []
    for _ in range(av.WALK_MAX):
        av.on_player_error(db, "150", db["videoId"])
        kinds.append(db["blocked_notice"]["kind"])
    assert kinds[:-1] == ["swapped"] * (av.WALK_MAX - 1) and kinds[-1] == "exhausted", kinds
    assert db["blocked_notice"]["from"] == "Driftwood Choir — live", "the notice names what the ORDER put on"

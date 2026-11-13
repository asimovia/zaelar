"""His HAND on the player's own control becomes the order — and nothing else does (V2-884 1b, C10 A1/A2).

The risks measured before this was built: the autoplay start reports `muted=true` while the order already says sound
(adopting it would turn «the browser blocks it» into «he muted it»), and a late or unapplied report could undo what he
had just asked by voice. So a field that declares `adopt` settles per mount: it is adopted ONLY when a report that acks
the current revision of its order key moves away from a value it had already CONFIRMED; the adoption runs the app's
internal action (`player_adopt`: a mute by hand is his kept mute, as the button), attributed to him. A new order on the
key or another video starts the agreement over; a report that acks less is an observation; a new mount starts
unsettled; `adopt` is refused on a shared app and must name an internal action. Disarmed (each named) → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from voice import screens
from widgets import state, state_decl, store
from widgets.youtube import data as yt

A = "desktop:aaa"
V1, V2 = "dQw4w9WgXcQ", "9bZkp7q19f0"


@pytest.fixture
def player(monkeypatch, tmp_path):
    from server import canvas_api
    from i18n import langs
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    state._reset_for_tests()
    screens._reset_for_tests()
    screens.attach(A)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["youtube"]}})
    screens.note_playing("youtube", A)
    db = yt._load()
    db.update(videoId=V1, title="Never Gonna", channel="Rick", paused=False, muted=False, mute_kept=False, volume=70)
    store.save("youtube", db)
    state.note_save("youtube", db)
    seen: list = []
    import voice.observer as obs
    real = obs.emit
    monkeypatch.setattr(obs, "emit", lambda kind, label, **k: seen.append((kind, label, k.get("extra") or {}))
                        or real(kind, label, **k))
    yield seen
    state._reset_for_tests()
    screens._reset_for_tests()


_N = {"n": 0}


def _say(patch, *, ack=None, mount="m1", full=False):
    """A report through the real route (`state_api.widget_state`): the adoption, if any, runs as his click would."""
    from widgets import state_api
    _N["n"] += 1
    body = {"dev": A, "mount": mount, "n": _N["n"], "full": full or _N["n"] == 1, "patch": patch,
            "ack": ack if ack is not None else state.stamp("youtube")}
    r = asyncio.run(state_api.widget_state("youtube", body))
    return r.status_code, json.loads(r.body)


@pytest.fixture(autouse=True)
def _fresh_n():
    _N["n"] = 0


def _order():
    return yt._load()


def test_the_autoplay_start_is_never_adopted(player):
    _say({"playing": True, "playing_id": V1, "muted": True, "volume": 70})
    _say({"muted": True})
    assert _order()["muted"] is False and _order()["mute_kept"] is False, "a blocked start was taken for his mute"
    assert yt.apply_action("captions_on", {})["audio_blocked"] is True, "the block is a fact, not an order"


def test_his_hand_after_the_player_confirmed_is_adopted_as_his_button(player):
    seen = player
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70})       # agreed: the player has sound
    _say({"muted": True})                                                          # he taps the player's speaker
    assert _order()["muted"] is True and _order()["mute_kept"] is True, "his mute by hand was not the card's"
    assert any(k == "widget" and lb == "action" and x.get("adopted") and x.get("src") == "user" for k, lb, x in seen)
    yt.apply_action("load", {"videoId": V2})
    assert _order()["muted"] is True, "his hand's mute did not survive the next video, as his button's does"


def test_his_hand_on_the_volume_is_adopted(player):
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70})
    _say({"volume": 35})
    assert _order()["volume"] == 35


def test_a_voice_order_the_player_did_not_obey_is_never_undone(player):
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70})       # agreed on «sound»
    before = state.stamp("youtube")
    yt.apply_action("mute", {})                                                    # he says «silencia»
    _say({"muted": False}, ack=before)              # the player has not applied it yet: a late report, old ack
    assert _order()["muted"] is True, "a late report undid his voice order"
    _say({"muted": False})                          # it acks the current order and still sounds: contradicted
    assert _order()["muted"] is True, "an order the player did not obey was adopted back (undone in silence)"


def test_another_video_starts_the_agreement_over(player):
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70})       # agreed on V1
    db = _order()
    db.update(videoId=V2)
    store.save("youtube", db)                                                      # another video, sound still ordered
    _say({"muted": True})                                                          # its autoplay start
    assert _order()["muted"] is False, "an agreement on the old video adopted the new one's muted start"


def test_a_new_mount_is_unsettled_until_it_agrees(player):
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70})       # agreed on m1
    _say({"playing": True, "muted": True, "volume": 70}, mount="m2", full=True)    # a reload that starts muted
    assert _order()["muted"] is False, "a new mount inherited the old one's agreement"


def test_adopt_is_declared_with_its_guards():
    man = json.load(open(yt.__file__.replace("data.py", "manifest.json")))
    assert state_decl.problem(man) is None
    shared = {**man, "screens": "shared"}
    assert "one-screen" in state_decl.problem(shared)
    not_internal = json.loads(json.dumps(man))
    not_internal["actions"]["player_adopt"]["internal"] = False
    assert "INTERNAL" in state_decl.problem(not_internal)
    bad_on = json.loads(json.dumps(man))
    bad_on["state"]["report"]["muted"]["settle_on"] = "nope"
    assert "settle_on" in state_decl.problem(bad_on)


def test_a_report_from_before_a_restart_settles_nothing(player):
    """A page that outlived the engine acks the OLD epoch: it may agree and then move, and still adopts nothing."""
    old = {"epoch": "an-engine-before-the-restart", "rev": 999}
    _say({"playing": True, "playing_id": V1, "muted": False, "volume": 70}, ack=old)
    _say({"muted": True}, ack=old)
    assert _order()["muted"] is False, "a report acking a previous engine adopted"

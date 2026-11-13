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


class Surface:
    """The client as it is: a patch carries the LAST revision the card applied (never the current one by itself);
    `applied()` acks what it has rendered; `hand=True` = the player had his hand. Everything goes through the real
    route (`state_api.widget_state`), so an adoption runs as his click would."""

    def __init__(self, mount="m1"):
        self.mount, self.n, self.ack, self.first = mount, 0, None, True

    def applied(self, patch=None, hand=False):
        self.ack = state.stamp("youtube")
        return self.say(patch or {}, hand=hand, full=True)

    def say(self, patch, *, hand=False, full=False, ack="keep"):
        from widgets import state_api
        self.n += 1
        body = {"dev": A, "mount": self.mount, "n": self.n, "full": full or self.first, "patch": patch,
                "ack": self.ack if ack == "keep" else ack, **({"hand": True} if hand else {})}
        self.first = False
        r = asyncio.run(state_api.widget_state("youtube", body))
        return r.status_code, json.loads(r.body)


def _order():
    return yt._load()


AGREED_SOUND = {"playing": True, "playing_id": V1, "muted": False, "volume": 70}


def test_the_autoplay_start_is_never_adopted(player):
    s = Surface()
    s.applied({"playing": True, "playing_id": V1, "muted": True, "volume": 70})
    s.say({"muted": True})
    assert _order()["muted"] is False and _order()["mute_kept"] is False, "a blocked start was taken for his mute"
    assert yt.apply_action("captions_on", {})["audio_blocked"] is True, "the block is a fact, not an order"


def test_a_rebuilt_player_starting_muted_is_never_adopted_even_after_an_agreement(player):
    """Audit P1-1: «pon el vídeo de X» finds nothing (or the same video) — the card rebuilds the SAME player, which
    starts muted (`mute=1`). The client forgets what the old player said; the door starts the agreement over."""
    s = Surface()
    s.applied(dict(AGREED_SOUND))                                                    # agreed: sound
    s.say({"playing": False, "playing_id": None, "muted": None, "volume": None})     # the rebuild forgets
    s.say({"muted": True, "volume": 70}, hand=True)                                  # the new player's muted start
    assert _order()["muted"] is False and _order()["mute_kept"] is False, \
        "the rebuilt player's muted start was adopted: every next video would start silent"


def test_his_hand_after_the_player_confirmed_is_adopted_as_his_button(player):
    seen = player
    s = Surface()
    s.applied(dict(AGREED_SOUND))
    s.say({"muted": True}, hand=True)                                                # he taps the player's speaker
    assert _order()["muted"] is True and _order()["mute_kept"] is True, "his mute by hand was not the card's"
    assert any(k == "widget" and lb == "action" and x.get("adopted") and x.get("src") == "user" for k, lb, x in seen)
    yt.apply_action("load", {"videoId": V2})
    assert _order()["muted"] is True, "his hand's mute did not survive the next video, as his button's does"


def test_a_browser_that_reverts_the_sound_on_its_own_is_not_his_hand(player):
    s = Surface()
    s.applied(dict(AGREED_SOUND))
    s.say({"muted": True})                                       # no hand: the browser took the sound back
    assert _order()["muted"] is False and _order()["mute_kept"] is False
    assert yt.apply_action("captions_on", {})["audio_blocked"] is True, "a revert by the browser is a block"


def test_a_volume_drag_adopts_where_his_hand_stops(player):
    s = Surface()
    s.applied(dict(AGREED_SOUND))
    for v in (65, 60, 50, 40, 30):                                # the drag: reports with the ack it had
        s.say({"volume": v}, hand=True)
    assert _order()["volume"] == 65                               # the first step is taken at once…
    s.applied({"volume": 30}, hand=True)                          # …and the settled report brings where he stopped
    assert _order()["volume"] == 30, "a drag left the card at its first intermediate value"
    s.applied({"volume": 30})
    s.say({"volume": 30})
    assert _order()["volume"] == 30


def test_a_voice_order_that_changes_nothing_still_starts_the_agreement_over(player):
    """Audit P2-1: agreed on muted; his hand's unmute report is late; he says «silencia» (already muted: the value does
    not move, the command does); the late report must not undo the order."""
    db = _order(); db["muted"] = True; store.save("youtube", db)
    s = Surface()
    s.applied({**AGREED_SOUND, "muted": True})
    yt.apply_action("mute", {})                                   # same value, a new command
    s.say({"muted": False}, hand=True)                            # the late report of his hand
    assert _order()["muted"] is True, "a late report undid a voice order that left the value as it was"


def test_a_voice_order_the_player_did_not_obey_is_never_undone(player):
    s = Surface()
    s.applied(dict(AGREED_SOUND))                                 # agreed on «sound»
    yt.apply_action("mute", {})                                   # he says «silencia»
    s.say({"muted": False}, hand=True)                            # a report from before it applied it
    assert _order()["muted"] is True, "a late report undid his voice order"
    s.applied({"muted": False}, hand=True)                        # it acks the order and still sounds
    assert _order()["muted"] is True, "an order the player did not obey was adopted back (undone in silence)"


def test_another_video_starts_the_agreement_over(player):
    s = Surface()
    s.applied(dict(AGREED_SOUND))                                 # agreed on V1
    db = _order(); db.update(videoId=V2); store.save("youtube", db)
    s.say({"muted": True}, hand=True)
    assert _order()["muted"] is False, "an agreement on the old video adopted the new one's muted start"


def test_a_new_mount_is_unsettled_until_it_agrees(player):
    Surface("m1").applied(dict(AGREED_SOUND))
    Surface("m2").applied({**AGREED_SOUND, "muted": True}, hand=True)   # a reload that starts muted
    assert _order()["muted"] is False, "a new mount inherited the old one's agreement"


def test_a_report_from_before_a_restart_settles_nothing(player):
    old = {"epoch": "an-engine-before-the-restart", "rev": 999}
    s = Surface()
    s.say(dict(AGREED_SOUND), ack=old)
    s.say({"muted": True}, hand=True, ack=old)
    assert _order()["muted"] is False, "a report acking a previous engine adopted"


def test_an_adoption_the_app_refused_is_not_lost(player, monkeypatch):
    from widgets import server_api
    real = server_api._dispatch
    calls = {"n": 0}

    async def _refuse_once(wid, action, payload):
        calls["n"] += 1
        return {"ok": False, "error": "busy"} if calls["n"] == 1 else await real(wid, action, payload)
    monkeypatch.setattr(server_api, "_dispatch", _refuse_once)
    s = Surface()
    s.applied(dict(AGREED_SOUND))
    s.say({"muted": True}, hand=True)
    assert _order()["muted"] is False and calls["n"] == 1
    s.say({"volume": 70, "muted": True}, hand=True)               # the next report of the same hand
    assert _order()["muted"] is True, "his hand was lost because the first adoption failed"


def test_adopt_is_declared_with_its_guards():
    man = json.load(open(yt.__file__.replace("data.py", "manifest.json")))
    assert state_decl.problem(man) is None
    shared = {**man, "screens": "shared"}
    assert "one-screen" in state_decl.problem(shared)
    not_internal = json.loads(json.dumps(man))
    not_internal["actions"]["player_adopt"]["internal"] = False
    assert "INTERNAL" in state_decl.problem(not_internal)
    bad_on = json.loads(json.dumps(man))
    bad_on["state"]["report"]["muted"]["settle_on"] = ["video", "nope"]
    assert "settle_on" in state_decl.problem(bad_on)



def test_an_order_written_without_a_command_still_starts_the_agreement_over(player):
    """The order key moved by a writer that bumps no command (another door, a migration): the agreement was given to
    the OLD order, so a report that still has the old value is contradicted, never adopted back."""
    s = Surface()
    s.applied(dict(AGREED_SOUND))
    db = _order(); db["muted"] = True; store.save("youtube", db)          # muted, with no command
    s.applied({"muted": False}, hand=True)
    assert _order()["muted"] is True, "an agreement given to the old order adopted the new one back"

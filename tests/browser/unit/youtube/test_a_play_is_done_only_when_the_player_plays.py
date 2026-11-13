"""A player act is done only when OUR player REPORTS it: the end states read the report, never the order (V2-884 1b).

The end states of `load/play_item/next/previous/play/pause/mute/unmute/volume_*/play_result` and of our own streams
name `report.<field>` — what the card's live surface said through the state door (`widgets/state.py`), on the screen
the app lives on. The order changes the store the moment the op runs, and a «Hecho» read from it was said over a player
that never moved (V2-873); the report the old `player_state` action wrote into that same store is retired.

Three readings, each deciding one thing: a report that acks the order and agrees → met; one that acks it and disagrees →
unmet (after the circuit's grace); none yet → PENDING (the act waits); none within `PENDING_S`, or no surface at all →
`no_ack` (asked, never confirmed). `expect: changed` takes its base from the report at the act's birth. A player error
and a stream's source are still the store's — the server writes them. Disarmed (each named) → red.
"""
from __future__ import annotations

import copy
import io
import json
import urllib.request

import pytest

from nucleo.circuit import baseline, reported, verify
from voice import screens
from widgets import state, store
from widgets.youtube import data as yt

A = "desktop:aaa"
V1, V2, V3 = "dQw4w9WgXcQ", "9bZkp7q19f0", "kJQP7kiw5Fk"
_MANIFEST = json.load(open(yt.__file__.replace("data.py", "manifest.json"), encoding="utf-8"))
#: The acts whose end state is the player's (C8 1b) — the order keys they must never read.
PLAYER_ACTS = ("load", "play_item", "next", "previous", "play", "pause", "mute", "unmute", "volume_up", "volume_down",
               "set_volume", "play_result", "play_local", "play_torrent")
ORDER_KEYS = ("videoId", "paused", "muted", "volume", "playing", "playing_id")


@pytest.fixture(autouse=True)
def player(monkeypatch, tmp_path):
    from server import canvas_api
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(
        json.dumps({"title": "Vídeo", "author_name": "Canal"}).encode()))
    state._reset_for_tests()
    screens._reset_for_tests()
    screens.attach(A)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["youtube"]}})
    screens.note_playing("youtube", A)
    db = yt._load()
    db.update(videoId=V1, title="uno", paused=False, muted=False, mute_kept=False, volume=70, player_error="",
              list=[{"videoId": V1, "title": "uno"}, {"videoId": V2, "title": "dos"}, {"videoId": V3, "title": "tres"}],
              pos=0)
    store.save("youtube", db)
    state.note_save("youtube", db)
    yield
    state._reset_for_tests()
    screens._reset_for_tests()


class Surface:
    """The client as it is: a patch carries the last revision it APPLIED; `applied()` acks the current one with the
    whole snapshot of what it shows (a full report replaces every field)."""

    def __init__(self, mount="m1"):
        self.mount, self.n, self.ack, self.shown = mount, 0, None, {}

    def applied(self, **fields):
        self.ack = state.stamp("youtube")
        return self.say(full=True, **fields)

    def say(self, full=False, **fields):
        self.n += 1
        self.shown.update(fields)
        full = full or self.n == 1
        code, got = state.report("youtube", {"dev": A, "mount": self.mount, "n": self.n, "full": full,
                                             "patch": dict(self.shown) if full else fields, "ack": self.ack})
        assert code == 200, got
        return got


def _dw(action: str, payload: dict | None = None):
    from nucleo.circuit import spec
    dw = spec.render("youtube", action, payload or {})
    assert dw is not None, f"{action} declares no end state"
    return dw


def _playing(s: Surface, vid=V1, **extra):
    s.applied(**{"playing": True, "playing_id": vid, "muted": False, "volume": 70, **extra})


def test_every_player_act_reads_the_report_never_the_order():
    for act in PLAYER_ACTS:
        clauses = verify._clauses(_MANIFEST["actions"][act]["done_when"])[1]
        assert any(reported.field_of(c) for c in clauses), f"{act} reads no report"
        bad = [c for c in clauses if str(c.get("field") or "") in ORDER_KEYS]
        assert not bad, f"{act} reads the ORDER: {bad}"
    assert "player_state" not in _MANIFEST["actions"], "the store-written report is retired (C8 1b)"


@pytest.mark.parametrize("action,payload", [("load", {"videoId": V2}), ("next", {}), ("play_item", {"item": "3"})])
def test_the_order_alone_meets_nothing_the_report_does(action, payload):
    s = Surface()
    _playing(s)
    dw = _dw(action, payload)
    assert dw["all"][0]["baseline"] == V1, "the base of «changed» is what the player reported at the act's birth"
    assert yt.apply_action(action, payload).get("ok")
    assert verify.check(dw) is None and reported.awaiting(dw) == reported.PENDING, "ordered, not confirmed: it WAITS"
    s.say(playing=True, playing_id=V1)                       # the OLD player, before it applied the order
    assert verify.check(dw) is None and reported.awaiting(dw) == reported.PENDING, "a report that acks less is not it"
    s.applied(playing=True, playing_id=yt._load()["videoId"])
    assert verify.check(dw) is True


@pytest.mark.parametrize("action", ["load", "next", "play_item", "play_result"])
def test_a_video_the_player_refused_is_not_done(action):
    s = Surface()
    _playing(s)
    dw = _dw(action, {"videoId": V2} if action == "load" else {"item": "2"} if action != "next" else {})
    db = yt._load()
    db.update(videoId=V2, player_error="150")
    store.save("youtube", db)
    state.note_save("youtube", db)
    s.applied(playing=True, playing_id=V2)
    assert verify.check(dw) is False, "the player reported an error: the video is not playing"


@pytest.mark.parametrize("action", ["play", "previous"])
def test_a_paused_player_is_not_playing(action):
    s = Surface()
    _playing(s, playing=False)
    dw = _dw(action)
    assert yt.apply_action(action, {}).get("ok")
    s.applied(playing=False, playing_id=V1)
    assert verify.check(dw) is False


def test_pause_mute_unmute_and_the_volume_are_done_when_the_player_says_so():
    s = Surface()
    _playing(s)
    for act, payload, contrary, agrees in (
            ("pause", {}, {"playing": True}, {"playing": False}),
            ("mute", {}, {"muted": False}, {"muted": True}),
            ("unmute", {}, {"muted": True}, {"muted": False}),
            ("set_volume", {"level": 30}, {"volume": 70}, {"volume": 30}),
            ("volume_up", {}, {"volume": 30}, {"volume": 45})):
        dw = _dw(act, payload)
        assert yt.apply_action(act, payload).get("ok"), act
        assert reported.awaiting(dw) == reported.PENDING, act
        s.applied(**contrary)
        assert verify.check(dw) is False, f"{act}: the player acked the order and did not obey"
        s.say(**agrees)
        assert verify.check(dw) is True, act


@pytest.mark.parametrize("action", ["play_local", "play_torrent"])
def test_a_stream_is_done_when_its_src_changed_and_it_plays(action):
    s = Surface()
    _playing(s)
    dw = copy.deepcopy(_MANIFEST["actions"][action]["done_when"])
    baseline.snapshot(dw)
    db = yt._load()
    db.update(src="/api/library/stream/a.mp4", source="local", videoId="", paused=False)
    store.save("youtube", db)
    state.note_save("youtube", db)
    s.applied(playing=False)
    assert verify.check(dw) is False, "our <video> said it does not play"
    s.say(playing=True)
    assert verify.check(dw) is True


def test_with_no_surface_reporting_the_act_reads_no_ack():
    """The text channel, a sandbox with no player, a screen gone: nothing reports the app — never done, never failed."""
    dw = _dw("play")
    assert verify.check(dw) is None and reported.awaiting(dw) == reported.NO_ACK
    s = Surface()
    _playing(s)
    assert verify.check(dw) is True and reported.awaiting(dw) == ""


def test_with_no_report_at_birth_the_base_of_changed_is_the_order():
    """A video started before any screen reported: «changed» compares with the video ORDERED then — never with nothing,
    which any id would differ from (the same video loaded again would read met)."""
    dw = _dw("load", {"videoId": V1})
    assert dw["all"][0]["baseline"] == V1
    s = Surface()
    s.applied(playing=True, playing_id=V1, muted=False, volume=70)
    assert verify.check(dw) is False, "the same video it already played is no change"


def test_past_the_ack_window_a_pending_field_reads_no_ack(monkeypatch):
    from widgets import state_render
    s = Surface()
    _playing(s)
    dw = _dw("pause")
    assert yt.apply_action("pause", {}).get("ok")
    monkeypatch.setattr(state_render, "PENDING_S", -1.0)
    assert reported.awaiting(dw) == reported.NO_ACK


def test_its_own_close_is_done_when_the_player_is_empty():
    """V2-873 (V7): the card's `close` empties the player; that — not the card closed — is its declared end state."""
    dw = _dw("close")
    assert verify.check(dw) is False
    assert yt.apply_action("close", {}).get("ok") is not False
    assert verify.check(dw) is True


# ── disarms ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_disarm_reading_the_order_meets_the_act_before_the_player_moved(monkeypatch):
    """Disarm: `report.<f>` read from the store again (the old way) → the order alone reads «met»."""
    s = Surface()
    _playing(s, playing=False)
    dw = _dw("play")
    assert yt.apply_action("play", {}).get("ok")
    from nucleo import truth
    monkeypatch.setattr(reported, "value", lambda c: not truth.widget_field("youtube", "paused"))
    assert reported.value(dw) is True, "the disarm did not land"
    assert verify.check(dw) is True, "read from the order, the act is met though the player never said so"


def test_disarm_a_pending_field_read_as_known_meets_on_the_old_player(monkeypatch):
    """Disarm: the ack ignored (pending read as known) → the old player's report meets a new video's start."""
    s = Surface()
    _playing(s)
    dw = _dw("pause")
    assert yt.apply_action("pause", {}).get("ok")
    s.say(playing=False)                                     # unacked: the old revision
    real = reported.read
    monkeypatch.setattr(reported, "read", lambda c: (reported.KNOWN, False) if real(c)[0] == reported.PENDING else real(c))
    assert verify.check(dw) is True, "an unacked report would confirm an order it never applied"

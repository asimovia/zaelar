"""The video player's state is what the PLAYER reports, never a flag the store kept (V2-884 1a, YouTube).

Measured (cloud sessions 2026-10-30 phone, 2026-11-11 desktop): `load` → the player reported `muted=true` 2-3 s later
(the autoplay start) → «el vídeo está sonando en silencio…» said within 30 ms → `muted=false` 0.5-1.3 s later → the
sentence said AGAIN over a video that was sounding; and once a stored `audio_blocked` outlived its condition for five
minutes. Now: YouTube declares its state (order · report · facts); `audio_blocked` is a FACT derived on every read from
what was ordered and what the player reports; its tell is armed when it turns on and withdrawn when it turns off
(a muted start that sounds within `SETTLE_S` is never said); the brain reads ONE state line (the digest says what is
loaded, never whether it plays); the player's ops answer `audio_blocked` from the fact; `player_audio` stores no flag.
Two desktops (`desktop:aaa`, `desktop:bbb`) and two tabs of one: the one-screen player is reported where it lives.
Disarmed (each named in the test) → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from voice import screens
from widgets import late_report, state, state_decl, state_render, store
from widgets.youtube import data as yt
from widgets.youtube import sound

A, B = "desktop:aaa", "desktop:bbb"
VID = "dQw4w9WgXcQ"


@pytest.fixture
def player(monkeypatch, tmp_path):
    from server import canvas_api
    from i18n import langs
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(langs, "current_code", lambda: "es")
    state._reset_for_tests()
    screens._reset_for_tests()
    import widgets.state_api  # noqa: F401 — the move listener
    for d in (A, B):
        screens.attach(d)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {A: {"open": ["youtube"]}, B: {"open": ["youtube"]}})
    screens.note_playing("youtube", A)
    db = yt._load()
    db.update(videoId=VID, title="Never Gonna", channel="Rick", paused=False, muted=False)
    store.save("youtube", db)
    state.note_save("youtube", db)
    monkeypatch.setattr(late_report, "_last_agent_order", {})
    yield
    state._reset_for_tests()
    screens._reset_for_tests()


def _report(n, patch, *, dev=A, mount="m1", full=False, ack=True):
    body = {"dev": dev, "mount": mount, "n": n, "full": full or n == 1, "patch": patch}
    if ack:
        body["ack"] = state.stamp("youtube")
    return state.report("youtube", body)


async def _route(n, patch, **k):
    from widgets import state_api
    body = {"dev": k.get("dev", A), "mount": k.get("mount", "m1"), "n": n, "full": n == 1, "patch": patch,
            "ack": state.stamp("youtube")}
    r = await state_api.widget_state("youtube", body)
    return r.status_code, json.loads(r.body)


def test_youtube_declares_its_state_and_derives_its_facts(player):
    assert state_decl.problem(json.load(open(yt.__file__.replace("data.py", "manifest.json")))) is None
    assert sound.facts({"muted": False}, {"playing": True, "muted": True}) == {"audio_blocked": True, "sound_on": False}
    assert sound.facts({"muted": True}, {"playing": True, "muted": True})["audio_blocked"] is False, \
        "his own mute read as blocked"
    assert sound.facts({"muted": False}, {"playing": True})["audio_blocked"] is False, "an unknown sound read as blocked"


def test_the_brain_reads_the_report_and_the_digest_no_state(player):
    assert state_render.clause("youtube") == "youtube: state unreported"
    _report(1, {"playing": True, "playing_id": VID, "muted": True, "volume": 80, "view": "player",
                "title": "Never Gonna"})
    assert state_render.clause("youtube") == ('youtube@computer: playing, playing_id=dQw4w9WgXcQ, muted, volume=80, '
                                              'view=player, title="Never Gonna" · facts: audio_blocked')
    digest = yt.prompt_digest()
    assert "EN EL REPRODUCTOR: «Never Gonna»" in digest
    assert not any(w in digest for w in ("reproduciéndose", "en pausa", "SONIDO", "silenciado")), digest
    assert yt.apply_action("captions_on", {})["audio_blocked"] is True, "an op answered «blocked» from a stored flag"
    _report(2, {"muted": False})
    assert yt.apply_action("captions_off", {})["audio_blocked"] is False


def test_player_audio_stores_no_flag_and_his_hand_unmutes_the_card(player):
    db = yt._load()
    db["muted"] = True
    store.save("youtube", db)
    db = yt._load()
    assert sound.player_audio("player_audio", {"muted": "true", "videoId": VID}, db) == {"ok": True}
    assert "audio_blocked" not in db and "audio_blocked" not in yt._load(), "a silence was stored as a flag"
    sound.player_audio("player_audio", {"muted": "false", "videoId": VID}, yt._load())
    assert yt._load()["muted"] is False, "his hand on the player's own control did not reach the card"


@pytest.fixture
def told(monkeypatch):
    said: list = []

    async def _notify(title, text, **kw):
        said.append(text)
        return True
    from nucleo.pulse import notices
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(late_report, "SETTLE_S", 0.05)
    return said


def test_a_muted_start_that_sounds_is_never_said_and_a_blocked_one_is_said_once(player, told):
    async def run(sounds: bool):
        late_report.note_agent_order("youtube")
        code, out = await _route(1, {"playing": True, "playing_id": VID, "muted": True})
        assert code == 200 and out["facts"] == ["audio_blocked"] and "_on" not in out
        if sounds:
            await _route(2, {"muted": False})
        await asyncio.sleep(0.15)
    asyncio.run(run(True))
    assert told == [], "the muted autoplay start was said over a video that sounded"
    state._reset_for_tests()
    asyncio.run(run(False))
    assert len(told) == 1 and "silencio" in told[0]


def test_two_desktops_and_two_tabs_report_where_the_player_lives(player):
    assert _report(1, {"playing": True}, dev=B)[0] == 409, "the desktop without the player reported it"
    assert _report(1, {"playing": True})[0] == 200
    assert _report(1, {"playing": False}, mount="tab2", full=True)[0] == 200, "a second tab's full snapshot"
    assert _report(5, {"playing": True}, mount="m1")[0] == 409, "the replaced tab took the player back"
    screens.note_playing("youtube", B)
    assert state.snapshots("youtube") == [] and state_render.clause("youtube") == "youtube: state unreported"
    assert _report(1, {"playing": True}, dev=B)[0] == 200
    assert state_render.clause("youtube").startswith("youtube@computer: playing")

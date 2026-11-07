"""A call to a PLAYER is served by its catalogue, never swallowed by an errand (V2-860 T1.1).

Measured on a phone (2026-11-07): «busca cuentos de Elena…, Sueña cuentos se llama el podcast» → the model called
`play_music`; the brief's `escalate_or_inline` said escalate at 0.62 (≥ the licence), so `gate_calls` dropped the call
and routed the request to a generic errand. The worker filled a results sheet by driving a headless browser at
open.spotify.com for seven minutes and found nothing, while the connected music catalogue answers in 350 ms.

The class: the routing gate protects SENDS (consent, V2-851 F5) and treated a player like one. Music goes to the music
card, video to the video card — they leave nothing outward. Now a player call runs under a sure escalate, its words are
said, and no errand opens behind it; any other call of the turn — before or after the player — is still routed. Which
tool is a player is read from `nucleo.acts.media.CARD_OF_TOOL` (one declaration). Disarm: `is_player` reading an
empty `CARD_OF_TOOL` → the call is swallowed again (red).
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo.acts.media import CARD_OF_TOOL
from nucleo.flash import follow_up_pass as FP
from nucleo.turn import brief as tb
from nucleo.turn import route_by_verdict as R

ORDER = "Pues busca cuentos de Elena Lostalé, Sueña cuentos se llama el podcast"


def _brief(conf=0.62):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t",
            "result": {"_call_id": "t", tb.ESCALATE_KEY: {"choice": "escalate", "confidence": conf, "probs": {}}}}


def _gate(brief):
    ran, events, req = [], [], {"v": None, "more": [], "surface": {}}
    call = R.gate_calls(lambda n, a: ran.append(n) or "ran", brief=brief, escalate_req=req, operator_text=ORDER,
                        emit=lambda *a, **k: events.append(a), t0=time.monotonic(), wait=0.0)
    return call, ran, req


@pytest.mark.parametrize("player", sorted(CARD_OF_TOOL))
def test_a_player_call_runs_under_a_sure_escalate_and_opens_no_errand(player):
    brief = _brief()
    call, ran, req = _gate(brief)
    assert call(player, {"query": "Sueña cuentos"}) == "ran" and ran == [player]
    assert not req.get("routed") and req["v"] is None, "no errand behind the player"
    assert R.player_ran(brief) == player
    assert R.sure_escalate(brief), "the verdict itself is untouched: only the player call is exempt"


def test_a_send_is_still_routed_under_the_same_verdict():
    call, ran, req = _gate(_brief())
    assert call("reply_message", {"text": "hola"}) is None and ran == [] and req["routed"]


def test_a_player_after_the_turn_was_routed_does_not_run_beside_the_errand():
    call, ran, req = _gate(_brief())
    call("reply_message", {})
    assert call("play_music", {"query": "x"}) is None and ran == [] and req["routed"]


def test_the_words_of_a_turn_a_player_took_are_said():
    brief = _brief()
    sent, events = [], []
    h = FP.Hold(brief, sent.append, route_wait_s=0.0)
    h.say("Lo busco en tu Spotify. ")              # the first word is held under the sure escalate…
    call, _ran, _req = _gate(brief)
    call("play_music", {"query": "Sueña cuentos"})  # …then the model hands the turn to the player
    asyncio.run(h.release([], (), lambda *a, **k: events.append(a)))
    assert "".join(sent).strip() == "Lo busco en tu Spotify." and not h.routed


def test_a_send_after_a_player_call_in_the_same_turn_is_still_routed():
    """The exemption is the player CALL, never the turn: a model that plays and sends in one turn still sends
    through its task (consent, V2-851 F5) — and the turn's words are then the errand's, not said inline."""
    brief = _brief()
    sent = []
    h = FP.Hold(brief, sent.append, route_wait_s=0.0)
    call, ran, req = _gate(brief)
    assert call("play_music", {"query": "Sueña cuentos"}) == "ran"
    assert call("reply_message", {"text": "hola"}) is None
    assert ran == ["play_music"] and req["routed"]
    h.say("Hecho, enviado. ")
    asyncio.run(h.release([], (), lambda *a, **k: None))
    assert "".join(sent).strip() == "", "a routed send's inline words are not said"


def test_the_phone_turn_replayed_records_the_play_and_opens_no_errand():
    """T96 of the archived phone session (fixture: the brief's verdicts and the model's call, nothing personal)."""
    import json
    from pathlib import Path
    fx = json.loads((Path(__file__).parent / "fixtures" / "v860_t96_player_under_escalate.json").read_text())
    from nucleo.flash.tool_executor_calls import _t_play_music
    for conf in (fx["escalate_confidence"], fx["escalate_confidence_reread"]):
        brief = _brief(conf=conf)
        assert R.sure_escalate(brief), "the replayed verdict is sure, as it was then"
        music_req, req = {"v": None}, {"v": None, "more": [], "surface": {}}
        call = R.gate_calls(lambda n, a: _t_play_music(args=a, music_req=music_req, _brief=brief, esc=req,
                                                        text=fx["operator_text"]),
                            brief=brief, escalate_req=req, operator_text=fx["operator_text"],
                            emit=lambda *a, **k: None, t0=time.monotonic(), wait=0.0)
        call(fx["call"]["name"], fx["call"]["args"])
        assert music_req["v"] == {"query": "Sueña cuentos", "action": "play"}, "the act's road records it"
        assert not req.get("routed") and req["v"] is None, "no errand"

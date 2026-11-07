"""A refused card action hands back its DECLARED payload, so whoever called it can call it right (V2-860 T2.7).

Measured in watch-a-video-not-listen-to-it__us: the model asked the video card `set_volume {}` (no `level`), the card
refused it as `bad_level`, and the refusal reached nobody who could act on it. Manifest payloads are prose
(`{"level": "0-100"}`), not a schema, so nothing coerces the call; the REFUSAL is what can carry level 2 of the
action — the declared shape and the field the call left out — at the one door every caller shares
(`widgets.server_api.brain_action`), read through `act_policy.declared_actions`. A worker's bridge forwards it beside
`detail/options/field`. Nothing is added to any prompt up front. Disarm: `action_shape.on_refusal` returning the card's
refusal untouched → red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from widgets import server_api as SA

YOUTUBE_SET_VOLUME = {"level": "0-100"}      # the declared payload of `youtube.set_volume` (manifest)


def test_the_video_cards_declared_volume_payload_is_the_one_this_test_names():
    from nucleo.flash.frontend import declared_actions
    assert declared_actions("youtube")["set_volume"]["payload"] == YOUTUBE_SET_VOLUME


def test_a_volume_with_no_level_is_refused_with_the_declared_shape():
    res = asyncio.run(SA.brain_action("youtube", "set_volume", {}))
    assert res.get("ok") is False and res.get("error") == "bad_level"
    assert res.get("payload") == YOUTUBE_SET_VOLUME and res.get("field") == "level"


def test_a_call_that_lands_carries_no_shape():
    res = asyncio.run(SA.brain_action("youtube", "set_volume", {"level": 30}))
    assert not res.get("error") and "payload" not in res


def test_a_worker_gets_the_shape_with_the_refusal(monkeypatch):
    from nucleo.cli import worker_api_exec as W
    rec = SimpleNamespace(task_id="7", trace_id="", sheet="")
    out = asyncio.run(W._exec_allow("widget_data", {"widget_id": "youtube", "action": "set_volume", "payload": {}},
                                    rec))
    assert out["ok"] is False and out["error"] == "bad_level"
    assert out["payload"] == YOUTUBE_SET_VOLUME and out["field"] == "level"

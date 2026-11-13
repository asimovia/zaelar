"""What he approved leaves byte-identical, whichever door his yes came through (V2-903 P1-1 + P1-A, node 2.232).

Two rewrites ran AFTER his yes, at the dispatch door every send crosses: a ~70-word es/en table that had a model
translate the text into the session language (retired by P1-1), and `meeting_time.align_payload`, which swapped the
times in `text` for the agenda's — measured by the audit: «…at 5:00 PM» in, «…at 4:30 PM» out, on words he had
dictated or been shown. It was asymmetric too: the card's button and a worker's act skipped it.

Now nothing between the held act (or the question that showed it) and the card's own `apply_action` touches it. The
double sits ONE LAYER LOWER than any rewriter (`server_api.brain_action`), and the act enters by each of its four real
doors: the send task, his spoken yes, the card's Yes button and a worker's act. Every case carries what a known
rewriter would change: a time a recent agenda op contradicts, in Spanish, English and Japanese, in an English session.
The time alignment still exists for a text the MODEL wrote, once, at composition — before it is held or shown.

Disarm: put the agenda-time alignment back in `widgets.dispatch_tag` → the send-task, spoken-yes and button cases go red, 10 of 14
(the worker's act never crossed it: that was the asymmetry).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

MEETING = {"id": "m1", "title": "Catch up with Avery", "date": "2026-11-14", "startTime": "16:30", "endTime": "17:15"}
OPS = [{"wid": "agenda", "action": "move_meeting", "payload": {"item": "Catch up with Avery", "newTime": "16:30"}}]
TEXTS = {
    "es": "Avery, ya estamos: nuestro catch up de mañana es a las 5:00 PM, nos vemos.",
    "en": "Avery, our catch up tomorrow is at 5:00 PM, see you then.",
    "ja": "Avery さん、明日の catch up は 5:00 PM です。",
}


@pytest.fixture
def world(monkeypatch):
    """An English session whose agenda just moved «Catch up with Avery» to 16:30, and a card whose door records."""
    from i18n import langs
    from nucleo.flash import meeting_time
    from widgets import server_api
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    monkeypatch.setattr(meeting_time, "_recent_ops", lambda: list(OPS))
    monkeypatch.setattr(meeting_time, "_meetings", lambda: [dict(MEETING)])
    got = []

    async def _card(wid, action, payload):
        got.append((wid, action, dict(payload)))
        return {"ok": True, "queued": True}
    monkeypatch.setattr(server_api, "brain_action", _card)
    return got


def _rewriter_would_touch(text: str) -> bool:
    from nucleo.flash import meeting_time
    return meeting_time.align(text, OPS, [MEETING])[1] != ""


def _sent(got, text):
    sends = [p for w, a, p in got if w == "mensajeria" and a == "send_to"]
    assert sends, f"the card's door was never reached: {got}"
    out = sends[-1].get("text")
    assert out.encode() == text.encode(), f"rewritten after his yes: {text!r} → {out!r}"


@pytest.mark.parametrize("lang", sorted(TEXTS))
def test_the_spoken_yes(world, lang):
    from voice.engine.llm.providers import pending_confirm
    from widgets import confirm
    text = TEXTS[lang]
    assert _rewriter_would_touch(text), "the case would not tell a rewrite apart"

    async def go():
        confirm.request("data", "mensajeria", "Send it?", op={"action": "send_to",
                                                             "payload": {"contact": "Avery", "text": text}},
                        notify_ui=False)
        assert pending_confirm._resolve_pending_confirm(True)
        for _ in range(20):
            await asyncio.sleep(0.02)
    asyncio.run(go())
    _sent(world, text)


@pytest.mark.parametrize("lang", sorted(TEXTS))
def test_the_cards_yes_button(world, lang):
    from widgets import confirm, server_api
    text = TEXTS[lang]

    async def go():
        confirm.request("data", "mensajeria", "Send it?", op={"action": "send_to",
                                                             "payload": {"contact": "Avery", "text": text}},
                        notify_ui=False)
        await server_api.confirm_widget("mensajeria", {"ok": True})
        for _ in range(20):
            await asyncio.sleep(0.02)
    asyncio.run(go())
    _sent(world, text)


@pytest.mark.parametrize("lang", sorted(TEXTS))
def test_a_workers_act(world, lang):
    from nucleo.cli import worker_api  # noqa: F401 — the bridge's import order
    from nucleo.cli import worker_api_exec
    text = TEXTS[lang]
    rec = SimpleNamespace(task_id="w-1", trace_id="", surface="", sheet="")
    asyncio.run(worker_api_exec._exec_allow(
        "widget_data", {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Avery", "text": text}},
        rec))
    _sent(world, text)


@pytest.mark.parametrize("lang", sorted(TEXTS))
def test_the_send_task(world, lang):
    """His dictated words, held on the row (`send_task.retain`), cross the exit door and the card's door as held."""
    from nucleo.request import send_task, send_task_run
    text = TEXTS[lang]
    uid = send_task.retain("mensajeria", "send_to", {"contact": "Avery", "text": text}, f"send Avery: {text}")
    assert uid and send_task.artefact(uid)["payload"]["text"] == text, "his words were changed when held"
    asyncio.run(send_task_run.run(uid))
    _sent(world, text)


def test_a_text_the_model_wrote_is_aligned_once_before_it_is_held(world):
    """The courtesy of V2-776 K1 survives where it belongs: on the model's own words, before anything is shown."""
    from nucleo.flash import meeting_time
    out = meeting_time.at_composition("mensajeria", "send_to", {"contact": "Avery", "text": TEXTS["en"]},
                                      "tell Avery the catch up is still on")
    assert "4:30 PM" in out["text"] and "5:00 PM" not in out["text"]


def test_the_dispatch_door_rewrites_nothing():
    import inspect

    import widgets
    assert "align_payload" not in inspect.getsource(widgets.dispatch_tag)

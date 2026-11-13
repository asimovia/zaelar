"""A verdict takes the PLACE of the model's call at VETO when what enters LEAVES or DELETES (CRIT-K2b R4, V2-893 L3).

Each reader below substitutes or vetoes what the model called: a move instead of a removal (`destructive_veto`), a
picture search instead of the model's tool (`picture_by_verdict`), his channel instead of the model's (`his_channel`), a
send task instead of the model's escalation (`identified` at `at_escalation`), an ordered send instead of the model's
draft (`ordered_instead`). Below VETO the verdict is a doubt and what the model called stands. Substituting by a
REVERSIBLE act (a draft for a reply) keeps the act floor. A send that enters in the model's place is born ASKING on its
row (rule 2). The band has ONE owner: when the model's escalation is the turn's, the close opens no send task. A channel
read below VETO against the call's is UNKNOWN — the exit asks. Disarm: each reader back to its old bar → red.
"""
from __future__ import annotations

import threading

import pytest

LOW, HIGH = 0.7, 0.9


def _brief(conf: float, open_ids=("mensajeria",), order: float | None = None, **answers) -> dict:
    ev = threading.Event()
    ev.set()
    res = {k: {"choice": c, "confidence": conf, "probs": {c: conf}} for k, c in answers.items()}
    if order is not None:
        res["request_type"] = {"choice": "order", "confidence": order, "probs": {"order": order}}
    return {"event": ev, "turn_id": "t-l3", "open_ids": list(open_ids), "judged": "x", "result": res}


def _destructive(conf):
    from nucleo.flash import destructive_veto
    return destructive_veto.instead(_brief(conf, ("youtube",), screen_action="youtube:move"), "youtube", "remove",
                                    "ponlo justo después del de skills") is not None


def _picture(conf, monkeypatch):
    from nucleo.flash import card_commission as cc
    monkeypatch.setattr(cc, "_filled_by_pictures", lambda wid: True)
    monkeypatch.setattr(cc, "picture_search_for", lambda wid, text: {"query": "gatos"})
    return cc.picture_by_verdict(_brief(conf, ("imagenes",), screen_action="imagenes:show"), "gatos") is not None


def _his_channel(conf):
    from nucleo.acts import message_channel
    out = message_channel.his_channel("mensajeria", "send_to", {"contact": "Pablo", "channel": "telegram"},
                                      _brief(conf, message_channel="whatsapp"))
    return out.get("channel") == "whatsapp"


def _send_task_instead_of_escalation(conf):
    from nucleo.request import send_task_turn
    from nucleo.turn import verdicts
    return send_task_turn.identified(_brief(conf, screen_action="mensajeria:send_to"), verdicts.VETO) != ("", "")


def _ordered_send(conf):
    from nucleo.acts import message_repair
    return message_repair.ordered_instead(_brief(conf, order=LOW, screen_action="mensajeria:forward"), "mensajeria",
                                          "draft", {"text": "ya lo estamos probando", "contact": "Quinn"},
                                          "mándale a Quinn la factura") is not None


READERS = {"destructive_veto": _destructive, "picture_by_verdict": _picture, "his_channel": _his_channel,
           "send_task_at_escalation": _send_task_instead_of_escalation, "ordered_send": _ordered_send}


@pytest.fixture
def quinn(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})


@pytest.mark.parametrize("reader", sorted(READERS))
def test_a_verdict_under_veto_never_takes_the_models_place(reader, monkeypatch, quinn):
    run = READERS[reader]
    args = (monkeypatch,) if reader == "picture_by_verdict" else ()
    assert run(LOW, *args) is False, f"{reader}: a {LOW} verdict took the model's place"
    assert run(HIGH, *args) is True, f"{reader}: a {HIGH} verdict did not take the model's place"


def test_a_reversible_act_in_a_leaving_calls_place_keeps_the_act_floor():
    """Audit L3 P1-3: the model's `reply` (it leaves) under a `draft` verdict at 0.7 — what enters is reversible, so it
    takes the place at the act floor; the reply never leaves on a doubt."""
    from nucleo.flash import tool_executor_widget_calls as tx
    ran = []
    got = tx._verdict_instead("mensajeria", "reply", {"text": "nos vemos el viernes"},
                              _brief(LOW, screen_action="mensajeria:draft"), "contéstale que nos vemos el viernes",
                              lambda *a, **k: None, {}, lambda w, a, p: ran.append(a), leaving=True)
    assert got is True and ran == ["draft"]


def test_the_ordered_send_under_a_sure_order_substitutes_and_is_born_asking(monkeypatch, quinn):
    """Audit L3 P1-1: the declared exception (an order sure at VETO, the act at the act floor — bench E3) substitutes,
    and the send that enters in the model's place waits on his yes on its row: nothing leaves on the substitution."""
    from nucleo import consent
    from nucleo.acts import message_repair
    from nucleo.request import send_task, send_task_who
    got = message_repair.ordered_instead(_brief(0.79, order=1.0, screen_action="mensajeria:forward"), "mensajeria",
                                         "draft", {"text": "ya lo estamos probando", "contact": "Quinn"},
                                         "mándale a Quinn la factura")
    assert got and got[0] == "forward", got
    asked, scheduled = [], []
    monkeypatch.setattr(send_task, "retain", lambda *a, **k: "row-1")
    monkeypatch.setattr(send_task, "artefact", lambda uid: {"widget": "mensajeria", "action": "forward",
                                                            "payload": {"contact": "Quinn", "text": "hola"}})
    monkeypatch.setattr(send_task, "missing", lambda art: ("", ""))
    monkeypatch.setattr(send_task_who, "which", lambda art, said: None)
    monkeypatch.setattr(send_task, "_question", lambda uid, art, slot, key, q="", c=None, consent="": asked.append(consent))
    monkeypatch.setattr(send_task, "_said_asked", lambda *a: None)
    monkeypatch.setattr(send_task, "_said_started", lambda *a: None)
    monkeypatch.setattr(send_task, "_schedule", lambda uid: scheduled.append(uid))
    from nucleo.request import substitution
    with substitution.in_the_models_place():
        assert send_task.commission("mensajeria", "forward", {}, "x") == "row-1"
    assert asked == [consent.ASK_CONSENT] and scheduled == [], "a substituted send left without his yes"
    asked.clear()
    send_task.commission("mensajeria", "forward", {}, "x")
    assert asked == [] and scheduled == ["row-1"], "the model's own send asks no more than before"


def test_the_band_has_one_owner_the_models_escalation(monkeypatch):
    """Audit L3 P1-2: with the model's escalation launched (`at_escalation` did not take it at 0.7), the close opens no
    send task for the same sentence."""
    import asyncio
    from nucleo.request import send_task_turn, send_task_words
    opened = []
    monkeypatch.setattr(send_task_words, "by_verdict", lambda *a, **k: opened.append(1) or ("row-1", "run"))
    brief = _brief(LOW, screen_action="mensajeria:send_to")
    got = asyncio.run(send_task_turn.at_close(brief, "x", "", {"v": "x"}, {"v": False}, lambda *a, **k: None, None))
    assert got == "" and opened == [], "two owners: the model's escalation and a send task"
    assert asyncio.run(send_task_turn.at_close(brief, "x", "", {"v": None}, {"v": False}, lambda *a, **k: None,
                                               None)) == "row-1"


def test_a_channel_read_below_veto_against_the_calls_asks():
    """Audit L3 P2-3: the call says telegram, his reading says whatsapp at 0.7 — neither replaced nor sent blind: the
    slot is UNKNOWN and the exit asks."""
    from nucleo.workers import exit_slots
    out = exit_slots.Reading({"contact": "Pablo", "channel": "telegram"})
    ctx = {"row_call": False, "wid": "mensajeria", "act": "send_to", "turn": _brief(LOW, message_channel="whatsapp"),
           "emit": lambda *a: None, "tainted": False, "said": "x"}
    exit_slots._reading(ctx, out, "channel", "channel")
    assert out.sources["channel"] == "unknown" and out.inner["channel"] == "telegram"


def test_a_repair_pass_send_is_licensed_not_substituted():
    """Audit L3 P2-1: the repair pass's own send is LICENSED by the verdict (R1) — it substitutes nothing, so the
    licence floor stands; a band verdict never drops his order."""
    from nucleo.flash import repair_grounding
    assert repair_grounding.send_backed_by_verdict(_brief(LOW, screen_action="mensajeria:send_to"), "mensajeria",
                                                   "send_to")


def test_a_doubt_is_recorded_not_asked(monkeypatch):
    """Between the licence and VETO the doubt is recorded (`against_the_model`) and nothing is asked."""
    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    assert _destructive(LOW) is False
    assert any((k.get("extra") or {}).get("kind_diag") == "doubt" for _a, k in seen), seen


def test_an_empty_channel_is_still_completed_at_the_licence():
    """No channel in the model's call: his reading COMPLETES it (R3) — only replacing the model's own needs VETO."""
    from nucleo.acts import message_channel
    out = message_channel.his_channel("mensajeria", "send_to", {"contact": "Pablo"},
                                      _brief(0.6, message_channel="whatsapp"))
    assert out.get("channel") == "whatsapp"

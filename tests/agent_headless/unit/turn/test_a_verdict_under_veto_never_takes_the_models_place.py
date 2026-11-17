"""A verdict takes the PLACE of the model's call at VETO when what enters LEAVES or DELETES (CRIT-K2b R4, V2-893 L3).

Each reader below substitutes or vetoes what the model called: a move instead of a removal (`destructive_veto`), a
picture search instead of the model's tool (`picture_by_verdict`), his channel instead of the model's (`his_channel`),
an ordered send instead of the model's draft (`ordered_instead`). Below VETO the verdict is a doubt and what the model
called stands. Disarm: each reader back to its old bar → red.
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


def _ordered_send(conf):
    from nucleo.acts import message_repair
    return message_repair.ordered_instead(_brief(conf, order=LOW, screen_action="mensajeria:forward"), "mensajeria",
                                          "draft", {"text": "ya lo estamos probando", "contact": "Quinn"},
                                          "mándale a Quinn la factura") is not None


READERS = {"destructive_veto": _destructive, "picture_by_verdict": _picture, "his_channel": _his_channel,
           "ordered_send": _ordered_send}


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

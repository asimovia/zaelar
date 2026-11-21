"""Who a send goes to is never a doubt — the one filter for acts that leave (the operator, 2026-10-15).

> «No podemos dejar con una duda quién es el destinatario de un email o de una reunión o de un mensaje, porque esos
> son unos asuntos que deben levantar un flag de confirmación de usuario […] un filtro único que básicamente es de
> evitar comprometer al usuario.»

Everything that does not leave runs on the operator's 70% with no permission question. An act that leaves the
machine (declared `external.send`) runs only when its recipient is certain:

  · named in HIS words, this turn or his recent ones — otherwise the leave gate asks «¿se lo mando a X?»;
  · resolved by the directory exactly, never by spelling tolerance — a near name is named back as a question;
  · and the engine never turns the model's draft into a send to somebody he did not name.

The meeting invitation is such an act too, so it declares `external.send` and walks through the same filter.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def gate(monkeypatch):
    from nucleo import his_words, untrusted
    from nucleo.acts import message as leave_gate
    his_words.reset()
    monkeypatch.setattr(untrusted, "present", lambda: False)
    yield leave_gate
    his_words.reset()


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Paco Ruiz", "kind": "person", "email": "paco@example.com",
                                    "channels": [{"platform": "email", "handle": "paco@example.com"}],
                                    "preferred": "email"})
    return cd


def test_a_near_name_is_named_back_never_written_to(directory):
    from widgets.mensajeria import outbound
    # V2-854: a spelling that SOUNDS the same («Pako») is the name; one that does not («Riuz») is only near.
    t = outbound.resolve_target({"contact": "Paco Riuz", "text": "hi", "channel": "email"})
    assert t["ok"] is False and t["near"] == ["Paco Ruiz"], t
    assert outbound.resolve_target({"contact": "paco ruiz", "text": "hi", "channel": "email"})["ok"] is True
    assert outbound.resolve_target({"contact": "Pako Ruiz", "text": "hi", "channel": "email"})["ok"] is True


def test_a_near_name_is_not_a_guest_either(directory):
    from widgets.agenda import invite
    g = invite.resolve_guests({"who": "Paco Riuz"})
    assert g["emails"] == [] and g["ambiguous"] and g["ambiguous"][0][1] == ["Paco Ruiz"], g
    assert invite.resolve_guests({"who": "paco ruiz"})["emails"] == ["paco@example.com"]


def test_two_channels_and_none_preferred_is_asked_in_his_language(directory, monkeypatch):
    """Which channel is a doubt too: nothing is sent, and the refusal is a sentence in the session's language."""
    directory.apply_action("add_contact", {"name": "Rowan Lee", "kind": "person", "email": "rowan@example.com",
                                           "channels": [{"platform": "email", "handle": "rowan@example.com"},
                                                        {"platform": "telegram", "handle": "@rowanlee"}]})
    from widgets.mensajeria import outbound
    from nucleo.request import refusal_line
    t = outbound.resolve_target({"contact": "Rowan Lee", "text": "hi"})
    assert t["ok"] is False and t["say"] == "widgets.mensajeria.refusal_which_channel", t
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert "none is marked as preferred" in refusal_line.speakable("mensajeria", t)

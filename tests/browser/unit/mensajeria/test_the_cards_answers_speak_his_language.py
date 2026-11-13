"""The messages card answers in HIS language (V2-880 follow-up): a refusal or an offer written as a Spanish literal in
the code reached an English speaker in Spanish — «WhatsApp no está conectado ahora mismo…», the offer of the contact's
other channels, «No hay ningún borrador…». Every answer is a key of the UI pack read through `words.say`.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
CARD = ENGINE / "widgets" / "mensajeria"


@pytest.mark.parametrize("code,down,offer", [
    ("en", "is not connected right now, so nothing was sent to Marta", "I can write to them on Telegram"),
    ("es", "no está conectado ahora mismo, así que no se ha enviado nada a Marta", "Por Telegram sí puedo escribirle"),
])
def test_a_send_on_a_channel_that_is_down_is_refused_and_offered_in_his_language(monkeypatch, code, down, offer):
    from i18n import runtime as rt
    from widgets.mensajeria.outbound import targets
    monkeypatch.setattr(rt, "active_code", lambda: code)
    out = targets.channel_down("Marta", "whatsapp", ["telegram"])
    assert out["error"] == "channel_down" and out["offer"] == ["telegram"]
    assert down in out["message"] and offer in out["message"], out["message"]


def test_no_answer_of_the_card_is_a_spanish_literal():
    """Every `"message": "…"` the card returns reads the pack: a literal is a sentence in one language."""
    found = []
    for py in CARD.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "message" and isinstance(v, (ast.Constant, ast.JoinedStr)):
                        found.append(f"{py.relative_to(ENGINE)}:{node.lineno}")
    assert not found, f"answers written as literals: {found}"


def test_every_key_the_card_says_is_in_both_packs():
    keys = set()
    for py in CARD.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_say" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                keys.add(node.args[0].value)
    assert len(keys) > 20, keys
    for lang in ("es", "en"):
        pack = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if f"widgets.mensajeria.{k}" not in pack)
        assert not missing, f"{lang}: {missing}"

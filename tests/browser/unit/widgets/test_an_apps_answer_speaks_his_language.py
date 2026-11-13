"""An app's answer is said in HIS language (V2-877 #10, the class): a refusal or an offer written as a Spanish literal in
an app's code («El navegador no está activo ahora mismo.», «No encontré ese vídeo.») reached an English speaker in
Spanish, and the model read it as the app's word. The door is `widgets/say.py` — the UI pack's `widgets.<app>.<key>`,
English when the pack has none.

The census below counts what is LEFT: an app's `message`/`error`/`say` answer written as a Spanish literal. It only
goes down; an app brought to zero stays there. Most of what remains are instructions to the model in model-facing
errors («vuelve a llamar a add_contact con `name`»), a translation backlog of their own.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
_SPANISH = re.compile(r"[áéíóúñ¿¡]|\b(está|hay|ningún|ninguna|dime|ahora|pude|encuentro|falta|vuelve|tengo|"
                      r"necesita|llamar|pásame|todavía|sin|dónde|cuál|qué)\b", re.I)

#: What each app still holds (2026-11-13). Lower a number when you translate; never raise one.
LEFT = {"agenda": 26, "archivos": 8, "contactos": 35, "documento": 7, "imagenes": 3, "mensajeria": 41,
        "(widgets)": 7}


def _census() -> dict[str, int]:
    out: dict[str, int] = {}
    for py in (ENGINE / "widgets").rglob("*.py"):
        if "_user" in py.parts or "_data" in py.parts:
            continue
        rel = py.relative_to(ENGINE / "widgets")
        app = rel.parts[0] if len(rel.parts) > 1 else "(widgets)"
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values):
                if not (isinstance(k, ast.Constant) and k.value in ("message", "error", "say")):
                    continue
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    text = v.value
                elif isinstance(v, ast.JoinedStr):
                    text = "".join(x.value for x in v.values if isinstance(x, ast.Constant))
                else:
                    continue
                if _SPANISH.search(text):
                    out[app] = out.get(app, 0) + 1
    return out


def test_no_app_holds_more_spanish_answers_than_it_did():
    now = _census()
    grew = {a: (n, LEFT.get(a, 0)) for a, n in now.items() if n > LEFT.get(a, 0)}
    assert not grew, f"answers written as Spanish literals (read the pack through widgets/say.py): {grew}"


@pytest.mark.parametrize("code,want", [("en", "The browser isn't running right now."),
                                        ("es", "El navegador no está activo ahora mismo.")])
def test_an_app_says_its_answer_in_the_active_language(monkeypatch, code, want):
    from i18n import runtime as rt
    from widgets.navegador import data as nav
    monkeypatch.setattr(rt, "active_code", lambda: code)
    assert nav.apply_action("open", {"url": "example.com"})["error"] == want

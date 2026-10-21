"""Every word meant for a human language lives in a language pack, never in a module (2026-10-21).

A `{"es": …, "en": …}` table or a `_ES`/`_EN` word list in product code is a language a third operator never gets:
onboarding generates the packs in `i18n/genesis/` for a new language, and nothing translates a module. Measured
before the packs: a French install heard English from 268 spoken lines and Spanish from the agenda, music and
connector tables, which fell back to `es` for anything they did not know.

The DECLARED exceptions are regex safety/routing vocabularies and model-facing prose with incident history behind
them (see `.meshkore/docs/architecture/zaelar-i18n.md`). Their counts can only shrink.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: path → how many tables it still carries. Only goes DOWN.
DECLARED = {
    "nucleo/flash/outgoing_lang.py": 1,
    "voice/engine/speech/say_numbers.py": 1,
    "widgets/results/digest.py": 1,        # the sheet digest is written for the model, in one language with its header
}

_WORDS = re.compile(r"[^\x00-\x7f]|[A-Za-z]{2,} [A-Za-z]")


def _human(node) -> bool:
    """A value made of human words (not codes like «es-ES» or voice ids)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return bool(_WORDS.search(node.value))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(isinstance(e, ast.Constant) and isinstance(e.value, str) and _WORDS.search(e.value)
                   for e in node.elts)
    if isinstance(node, ast.Dict):
        return any(_human(v) for v in node.values)
    return False


def _tables(src: str) -> int:
    n = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"es", "en"} <= keys and any(_human(v) for v in node.values):
                n += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and re.search(r"_(ES|EN)$", t.id) for t in targets) \
                    and _human(node.value):
                n += 1
    return n


def _product_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return [f for f in out if not f.startswith(("tests/", "i18n/")) and "/_user/" not in f]


def test_no_module_carries_a_language_table():
    found = {}
    for f in _product_files():
        try:
            n = _tables((ENGINE / f).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        if n > DECLARED.get(f, 0):
            found[f] = n
    assert not found, (f"words for one language inside a module: {found} — they go to i18n/genesis/<code>/ "
                       "(ui.json for the screen, voice.json for what the agent says, read with "
                       "`runtime.text` / `langs.words`), so onboarding can generate them for every language")


def test_the_detector_sees_a_table():
    assert _tables('_M = {"es": "No hay nada.", "en": "Nothing there."}') == 1
    assert _tables('_DAYS_ES = ("lunes", "martes")') == 0          # single words: a code-like tuple…
    assert _tables('_DAYS_ES = ("miércoles", "sábado")') == 1        # …unless it is clearly a language
    assert _tables('_R = {"es": "es-ES", "en": "en-US"}') == 0       # locale codes are not words

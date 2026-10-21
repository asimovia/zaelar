"""The boot screen speaks the instance's language, never the browser's (2026-10-21).

A reload of an English instance in a Spanish browser showed «Preparando tu agente»: `preboot.js` chose its language
from `navigator.language` and carried Spanish inline. Its strings now live in the bundles (`preboot.*`), it reads the
bundle the last visit cached for the instance's language, and falls back to an English floor — never to the browser.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_suffix(".mjs")
PREBOOT = ENGINE / "frontend" / "app" / "core" / "preboot.js"


def _bundle(code: str) -> dict:
    return json.loads((ENGINE / "i18n" / "bundles" / f"{code}.json").read_text(encoding="utf-8"))


def _title(lang: str, browser: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to run preboot.js")
    out = subprocess.run([node, str(SCRIPT), lang, browser], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_a_fresh_visit_is_english_whatever_the_browser_says():
    assert _title("", "es-ES") == _bundle("en")["preboot.boot.title"]


def test_the_instance_language_wins_over_the_browser():
    assert _title("zh", "es-ES") == "BUNDLE:zh"
    assert _title("en", "es-ES") != _bundle("es")["preboot.boot.title"]


def test_the_english_floor_is_the_base_bundle_and_every_preset_has_it():
    src = PREBOOT.read_text(encoding="utf-8")
    floor = dict(re.findall(r'^\s*"(preboot\.[\w.]+)":\s*("(?:[^"\\]|\\.)*")', src, re.M))
    floor = {k: json.loads(v) for k, v in floor.items()}
    en, es = _bundle("en"), _bundle("es")
    assert floor, "the English floor vanished from preboot.js"
    assert {k: en.get(k) for k in floor} == floor, "the inline floor drifted from en.json"
    assert not [k for k in floor if k not in es], "a preboot string has no Spanish"
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith(("//", "*", "/*")))
    assert "navigator.language" not in code, "the boot screen reads the browser's language again"

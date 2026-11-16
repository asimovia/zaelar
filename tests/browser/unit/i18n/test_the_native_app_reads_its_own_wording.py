"""Inside the native companion a string reads its `<key>@app` sibling (see the .mjs file for the runtime contract).

The second half holds the DATA: every sibling has its plain key, and every string of the phone shell (`mobile.*`)
never names the screens «apps» (INI-068: they are widgets everywhere), in each preset language.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_native_app_reads_its_own_wording.mjs")
GENESIS = Path(__file__).resolve().parents[4] / "i18n" / "genesis"
SIBLING = "@app"
NAMES_APPS = re.compile(r"\bapps?\b|\baplicaci", re.IGNORECASE)


def _bundle(code: str) -> dict:
    return json.loads((GENESIS / code / "ui.json").read_text(encoding="utf-8"))


def test_inside_the_app_t_reads_the_sibling_and_a_browser_never_does() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the i18n surface contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("code", ["en", "es"])
def test_every_sibling_has_its_plain_key(code: str) -> None:
    b = _bundle(code)
    orphans = [k for k in b if k.endswith(SIBLING) and k[: -len(SIBLING)] not in b]
    assert not orphans, f"{code}: siblings with no plain key: {orphans}"


@pytest.mark.parametrize("code", ["en", "es"])
def test_no_phone_shell_string_names_the_widgets_apps(code: str) -> None:
    """INI-068 (2026-11-13, applied to the phone shell 2026-11-16): the screens are «widgets» in every surface, the app
    included, so a phone-shell string never names them «apps» — plain or `@app` sibling. The sibling mechanism stays for
    any other wording the native app must say differently."""
    b = _bundle(code)
    named = [k for k, v in b.items() if k.startswith("mobile.") and NAMES_APPS.search(v)]
    assert not named, f"{code}: phone-shell strings that still call the widgets apps: {named}"

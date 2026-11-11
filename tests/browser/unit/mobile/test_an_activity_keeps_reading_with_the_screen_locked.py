"""V2-890 — pytest face of the .mjs next to it, plus the gate: a generated app reaches sensors only through ctx.device."""

import shutil
import subprocess
from pathlib import Path

import pytest

from widgets.validator_js import _scan_widget_js as validate_js_source

SCRIPT = Path(__file__).with_name("test_an_activity_keeps_reading_with_the_screen_locked.mjs")


def test_an_activity_keeps_reading_with_the_screen_locked_and_hands_over_what_was_missed() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    r = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("line", [
    "const p = window.Capacitor.Plugins.ZaelarDevice;",
    "navigator.geolocation.getCurrentPosition(f);",
    "navigator . bluetooth.requestDevice({});",
])
def test_a_generated_app_never_reaches_a_native_api_directly(line: str) -> None:
    errors = validate_js_source(f"export function render(el, data, ctx) {{ {line} }}")
    assert errors, f"the gate let through: {line}"


def test_the_sanctioned_door_passes_the_gate() -> None:
    src = "export async function render(el, data, ctx) { const d = await ctx.device(); await d.details(); }"
    assert not validate_js_source(src)

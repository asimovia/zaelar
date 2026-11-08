"""A stopped agent locks the desktop (operator, 2026-11-08).

Measured on his engine: with ⏻ off the cards stayed fully interactive. He paused the music card, then tapped ▶ four
times; the server refused each tap (`producers.gate` → `agent_stopped`) and nothing on screen said so — a card that
looked alive over a stopped agent, half on and half off. His words: «que cuando el agente está parado el escritorio
se bloquee… un overlay sombreado y que tengamos claro que está parado».

The veil is a native surface over the widget stage: shown for `off` and the two transits, swallowing the cards'
clicks, BELOW the bottom rail and the orb (how he switches it back on), with its own ⏻ through the one power door.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

VEIL = Path("frontend/app/components/PowerVeil.js")
SURFACES = Path("frontend/app/core/system-surfaces.js")
CSS = Path("frontend/app/styles.css")
DESKTOP = Path("frontend/app/widgets/desktop.js")
RAIL = Path("frontend/app/components/WidgetRail.js")


def _z(src: str, selector_re: str) -> int:
    m = re.search(selector_re + r"\{[^}]*?z-index:(\d+)", src)
    assert m, f"no z-index for {selector_re}"
    return int(m.group(1))


def test_the_veil_is_a_registered_native_surface_on_the_desk():
    src = SURFACES.read_text(encoding="utf-8")
    assert 'import { PowerVeil } from "../components/PowerVeil.js' in src
    assert re.search(r'id: "power-veil",\s*comp: PowerVeil,\s*target: "desk"', src)


def test_the_veil_covers_the_cards_and_leaves_the_rail_and_the_orb_above_it():
    css = CSS.read_text(encoding="utf-8")
    veil = _z(css, r"\.power-veil")
    stage = _z(DESKTOP.read_text(encoding="utf-8"), r"\.hb-stage")
    rail = _z(RAIL.read_text(encoding="utf-8"), r"#wrail")
    orb = _z(css, r"\.orbwrap")
    assert stage < veil < rail < orb, (stage, veil, rail, orb)


def test_the_way_out_is_the_one_power_door():
    src = VEIL.read_text(encoding="utf-8")
    assert 'from "../services/power.js' in src and 'setPower(false, "veil")' in src


@pytest.mark.parametrize("lang", ["en", "es"])
def test_every_line_of_the_veil_is_in_the_ui_pack(lang):
    pack = json.loads(Path(f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
    used = set(re.findall(r't\("(veil\.[a-z_]+)"\)', VEIL.read_text(encoding="utf-8")))
    assert used and not (used - set(pack)), sorted(used - set(pack))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_veil_shows_for_stopped_and_the_transits_only():
    src = VEIL.read_text(encoding="utf-8")
    fn = src[src.index("export function veilFace"):src.index("export function PowerVeil")]
    script = fn.replace("export function", "function") + """
const cases = [["off",true,"off"],["off",false,"off"],["pausing",true,"pausing"],["starting",true,"starting"],
  ["starting",false,""],["live",true,""],["remote",true,""],["stalled",true,""]];
for (const [s,b,want] of cases) { const got = veilFace(s,b); if (got !== want) { console.error(s,b,got,want); process.exit(1); } }
"""
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr

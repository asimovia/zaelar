"""The «Clusters» column of the side panel is a component of its own (`frontend/side/clusters/`, V2-086).

It imports nothing from outside its folder — no store, api, session or i18n: everything comes through the bridge it
is mounted with — and nothing but its one bridge (`frontend/app/services/clusters-bridge.js`) imports it. What a row and the gate
say (`rowView`, `gateView`) runs under Node: `test_the_clusters_model.mjs`.

Disarms seen red: an import of the store added to the component; a second file importing it; the singular and plural
peer words swapped.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
FOLDER = ENGINE / "frontend/side/clusters"
SCRIPT = Path(__file__).with_name("test_the_clusters_model.mjs")
BRIDGE = "frontend/app/services/clusters-bridge.js"
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"]([^'"]+)['"]""")


def test_the_component_imports_nothing_from_outside_its_folder():
    found = {}
    for p in sorted(FOLDER.glob("*.js")):
        for spec in IMPORT.findall(p.read_text(encoding="utf-8")):
            if not spec.startswith("./") or "/" in spec[2:]:
                found.setdefault(p.name, []).append(spec)
    assert not found, f"the column reaches outside its folder: {found}"
    assert {p.name for p in FOLDER.glob("*.js")} == {"clusters.js"}


def test_nothing_but_its_bridge_imports_the_component():
    users = []
    for base in ("frontend", "widgets"):
        for p in (ENGINE / base).rglob("*.js"):
            rel = p.relative_to(ENGINE).as_posix()
            if rel.startswith("frontend/side/clusters/") or "vendor" in p.parts:
                continue
            if any("side/clusters/" in s for s in IMPORT.findall(p.read_text(encoding="utf-8", errors="ignore"))):
                users.append(rel)
    assert users == [BRIDGE], users


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_what_a_row_and_the_gate_say():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

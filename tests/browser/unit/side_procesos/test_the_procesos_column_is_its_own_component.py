"""The «Procesos» column of the side panel is a component of its own (`frontend/side/procesos/`).

Three things, read from the source and measured under Node:

  · the component imports nothing from outside its folder — no store, api, session or words: everything reaches it
    through the bridge it is mounted with;
  · nothing imports it but that bridge (`frontend/app/services/procesos-bridge.js`);
  · its model says what each row means (`test_the_procesos_rows_say_what_happened.mjs`): a finished row never
    paints an unknown ending as ✓, a running row's title holds still, the pulse's facts reach the meta line.

Disarms seen red: `procesos.js` importing `../../app/core/store.js`; a widget importing the component directly;
the model folding an unknown ending into «done».
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("test_the_procesos_rows_say_what_happened.mjs")
FOLDER = ENGINE / "frontend/side/procesos"
#: the only file outside the folder that may import the component: its one bridge
BRIDGES: frozenset[str] = frozenset({"frontend/app/services/procesos-bridge.js"})
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"]([^'"]+)['"]""")


def test_the_component_imports_nothing_from_outside_its_folder():
    found = {}
    for p in sorted(FOLDER.glob("*.js")):
        for spec in IMPORT.findall(p.read_text(encoding="utf-8")):
            if not spec.startswith("./") or "/" in spec[2:]:
                found.setdefault(p.name, []).append(spec)
    assert not found, f"the procesos column reaches outside its folder: {found}"
    assert {p.name for p in FOLDER.glob("*.js")} >= {"procesos.js", "model.js"}
    assert (FOLDER / "procesos.css").is_file(), "its look travels with it"


def test_nothing_but_its_bridge_imports_the_component():
    users = []
    for base in ("frontend", "widgets"):
        for p in (ENGINE / base).rglob("*.js"):
            rel = p.relative_to(ENGINE).as_posix()
            if rel.startswith("frontend/side/procesos/") or "vendor" in p.parts:
                continue
            if "side/procesos/" in p.read_text(encoding="utf-8", errors="ignore") and rel not in BRIDGES:
                users.append(rel)
    assert not users, users
    bridge = (ENGINE / "frontend/app/services/procesos-bridge.js").read_text(encoding="utf-8")
    assert "side/procesos/procesos.js" in bridge, "the bridge is what mounts it"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_each_row_says_what_happened():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

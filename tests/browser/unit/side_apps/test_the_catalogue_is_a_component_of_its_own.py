"""The side panel's widget catalogue (System · Custom) is a component of its own: `frontend/side/apps/`.

  · it imports nothing from outside its folder, and nothing imports it but its one bridge (`services/apps-bridge.js`);
  · its model (which rows are widgets, which scope each lands in, by name) holds under Node
    (`test_the_catalogue_model_splits_by_builder.mjs`).

Disarms seen red: the component importing `../../app/core/store.js`; a second file importing `side/apps/`; the
model listing a forked widget only under Custom.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
FOLDER = ENGINE / "frontend/side/apps"
SCRIPT = Path(__file__).with_name("test_the_catalogue_model_splits_by_builder.mjs")
#: the only file outside the folder that may import the component: its one bridge
BRIDGES: frozenset[str] = frozenset({"frontend/app/services/apps-bridge.js"})
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"]([^'"]+)['"]""")


def test_the_component_imports_nothing_from_outside_its_folder():
    found = {}
    for p in sorted(FOLDER.glob("*.js")):
        for spec in IMPORT.findall(p.read_text(encoding="utf-8")):
            if not spec.startswith("./") or "/" in spec[2:]:
                found.setdefault(p.name, []).append(spec)
    assert not found, f"the catalogue reaches outside its folder: {found}"
    assert {p.name for p in FOLDER.glob("*.js")} >= {"apps.js", "model.js"}


def test_nothing_but_its_bridge_imports_the_component():
    users = []
    for base in ("frontend", "widgets"):
        for p in (ENGINE / base).rglob("*.js"):
            rel = p.relative_to(ENGINE).as_posix()
            if rel.startswith("frontend/side/apps/") or "vendor" in p.parts:
                continue
            specs = IMPORT.findall(p.read_text(encoding="utf-8", errors="ignore"))
            if any("side/apps/" in s for s in specs) and rel not in BRIDGES:
                users.append(rel)
    assert not users, users


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_model_splits_the_rows_by_who_built_them():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")

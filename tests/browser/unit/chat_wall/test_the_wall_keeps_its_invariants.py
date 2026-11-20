"""The chat wall's model keeps its invariants under thousands of random actions, and the component imports nothing
from outside its folder (INI-042 #49, plan of the wall §2, M1–M6, M9, M10).

The model's half runs under Node (`test_the_wall_keeps_its_invariants.mjs`): four writers, random actions, a forged
owner now and then, every invariant checked after every action. M10 is read from the source: every import of
`frontend/chat-wall/` names a file of that folder, and nothing outside it imports the component but its bridge.

Disarms seen red: a writer allowed to update a line it does not own (M3); an append inserted at the top (M2); a final
line of his updatable (M4); a forged owner taken (the forged-owner check).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("test_the_wall_keeps_its_invariants.mjs")
WALL = ENGINE / "frontend/chat-wall"
#: the only files outside the folder that may import the component (the plan's one bridge; none yet)
BRIDGES: frozenset[str] = frozenset()
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"]([^'"]+)['"]""")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_random_actions_keep_every_invariant():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_component_imports_nothing_from_outside_its_folder():
    found = {}
    for p in sorted(WALL.glob("*.js")):
        for spec in IMPORT.findall(p.read_text(encoding="utf-8")):
            if not spec.startswith("./") or "/" in spec[2:]:
                found.setdefault(p.name, []).append(spec)
    assert not found, f"the wall reaches outside its folder (M10): {found}"
    assert {p.name for p in WALL.glob("*.js")} >= {"chat-wall.js", "model.js", "view.js"}


def test_nothing_but_its_bridge_imports_the_component():
    users = []
    for base in ("frontend", "widgets"):
        for p in (ENGINE / base).rglob("*.js"):
            rel = p.relative_to(ENGINE).as_posix()
            if rel.startswith("frontend/chat-wall/") or "vendor" in p.parts:
                continue
            if "chat-wall/" in p.read_text(encoding="utf-8", errors="ignore") and rel not in BRIDGES:
                users.append(rel)
    assert not users, users

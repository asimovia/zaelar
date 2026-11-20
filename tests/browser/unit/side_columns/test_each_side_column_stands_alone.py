"""Each column of the side panel is a component of its own (INI-042 #49): `frontend/side/conectores/` and
`frontend/side/red/` import nothing from outside their folder (no store, api, session or i18n — everything comes
through the bridge handed to `mount`), and nothing imports a column but its one bridge in `frontend/app/services/`.
Their models are checked in Node (`test_the_side_column_models.mjs`).

Disarm: an import of the store added to a column, or a second file importing it → red."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("test_the_side_column_models.mjs")
#: column → (its folder's files, the ONE file outside the folder that may import it)
COLUMNS = {"conectores": ({"conectores.js", "model.js", "conectores.css"}, "frontend/app/services/conectores-bridge.js"),
           "red": ({"red.js", "model.js", "red.css"}, "frontend/app/services/red-bridge.js")}
IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"]([^'"]+)['"]""")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_column_models_hold():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


@pytest.mark.parametrize("column", sorted(COLUMNS))
def test_the_column_imports_nothing_from_outside_its_folder(column):
    folder = ENGINE / "frontend" / "side" / column
    found = {}
    for p in sorted(folder.glob("*.js")):
        for spec in IMPORT.findall(p.read_text(encoding="utf-8")):
            if not spec.startswith("./") or "/" in spec[2:]:
                found.setdefault(p.name, []).append(spec)
    assert not found, f"the {column} column reaches outside its folder: {found}"
    assert {p.name for p in folder.iterdir()} >= COLUMNS[column][0]


@pytest.mark.parametrize("column", sorted(COLUMNS))
def test_nothing_but_its_bridge_imports_the_column(column):
    users = []
    for base in ("frontend", "widgets"):
        for p in (ENGINE / base).rglob("*.js"):
            rel = p.relative_to(ENGINE).as_posix()
            if rel.startswith(f"frontend/side/{column}/") or "vendor" in p.parts:
                continue
            specs = IMPORT.findall(p.read_text(encoding="utf-8", errors="ignore"))
            if any(f"side/{column}/" in s for s in specs) and rel != COLUMNS[column][1]:
                users.append(rel)
    assert not users, users

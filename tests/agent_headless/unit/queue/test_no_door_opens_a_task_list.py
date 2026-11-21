"""No door opens a task list (INI-078, Q-7): several things asked at once are several independent tasks.

The list executor (`nucleo/batch`) had five doors — a consequence door at the turn, an HTTP route, a resume at boot, a
playbook a worker could be told to follow and a lane of the old turn. Each pin below is one of those doors, read from
what the engine DECLARES (its consequence table, its mounted routes, its playbooks) and from its own sources, so a door
put back by any route turns this red.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
#: an import of the list package, in any of its spellings
IMPORTS = re.compile(r"\bnucleo\.batch\b|from\s+nucleo\s+import\s+[^\n]*\bbatch\b")
#: what is not engine code: the tests, the environment, generated or vendored trees
OUTSIDE = ("tests", ".venv", ".git", "node_modules", "__pycache__", ".meshkore")


def _sources():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT)
        if not rel.parts or rel.parts[0] in OUTSIDE or any(part in OUTSIDE for part in rel.parts):
            continue
        yield rel, p


def test_the_list_package_is_gone():
    assert importlib.util.find_spec("nucleo.batch") is None


def test_no_engine_source_imports_it():
    hits = [f"{rel}:{n}" for rel, p in _sources()
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if IMPORTS.search(line)]
    assert hits == []


def test_every_consequence_door_reaches_a_live_funnel_and_none_takes_a_list():
    from nucleo import consequence
    for name, door in consequence.DOORS.items():
        module, _, attr = door.funnel.partition(":")
        assert not module.startswith("nucleo.batch"), name
        assert hasattr(importlib.import_module(module), attr), f"{name}: {door.funnel} is not a live funnel"


def test_no_route_takes_a_list():
    from server import create_app
    paths = {getattr(r, "path", "") for r in create_app().routes}
    assert not [p for p in paths if p.startswith("/api/lists")]


def test_no_playbook_walks_a_list():
    from nucleo.workers.prompts import playbook
    assert "lista" not in playbook.NAMES and "lista" not in playbook.DELIVERABLE


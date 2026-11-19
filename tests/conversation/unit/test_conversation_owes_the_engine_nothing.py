"""`conversation/` imports nothing of the engine, and the engine's workers import nothing of it (node 13.1).

The manager is tested by feeding it whatever we want at whatever speed, through its seven ports. That only holds if
nothing of the engine leaks in: every import of every module of the package — top level and lazy, read from the AST —
is the package itself or the standard library. Stronger than `search/`'s ratchet, which allows some leaves: here
there is no allowed list. And the other direction: a worker or the dispatcher never reaches into the manager — they
talk to it by envelopes and ids only (`worker.update` in, `task.start` out).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
PKG = ENGINE / "conversation"
NAMED = ("nucleo", "voice", "livekit", "memory", "widgets", "connectors", "server", "bus", "search")


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module


def _top(name: str) -> str:
    return name.split(".")[0]


def test_every_import_of_the_package_is_itself_or_the_standard_library():
    files = sorted(PKG.rglob("*.py"))
    assert len(files) >= 6, "the package is not where the ratchet reads it"
    bad = [f"{p.relative_to(ENGINE)}: {m}" for p in files for m in _imports(p)
           if _top(m) != "conversation" and _top(m) not in sys.stdlib_module_names]
    assert not bad, "the conversation package imports outside itself and the standard library:\n  " + "\n  ".join(bad)


def test_none_of_the_named_engine_packages_is_imported():
    bad = [f"{p.relative_to(ENGINE)}: {m}" for p in sorted(PKG.rglob("*.py")) for m in _imports(p)
           if _top(m) in NAMED]
    assert not bad, bad


def test_the_workers_and_the_dispatcher_do_not_import_the_manager():
    bad = [f"{p.relative_to(ENGINE)}: {m}"
           for sub in ("nucleo/workers", "nucleo/dispatch") for p in sorted((ENGINE / sub).rglob("*.py"))
           for m in _imports(p) if _top(m) == "conversation"]
    assert not bad, bad

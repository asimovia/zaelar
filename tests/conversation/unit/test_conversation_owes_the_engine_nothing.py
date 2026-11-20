"""`conversation/` imports nothing of the engine, and the engine's workers import nothing of it (node 13.1).

The manager is tested by feeding it whatever we want at whatever speed, through its seven ports. That only holds if
nothing of the engine leaks in: every import of every module of the package — top level and lazy, read from the AST —
is the package itself or the standard library. Stronger than `search/`'s ratchet, which allows some leaves: here
there is no allowed list. And the other direction: a worker or the dispatcher never reaches into the manager — they
talk to it by envelopes and ids only.

Its text owes nothing to our private notes either: the package is public, so no comment or docstring cites the ids of
an internal review, audit or design round (`MINOR 3`, `B4`, `PA-9`, `plan §15`…) — the reason is written in words. What
it may cite is public: the invariants I1–I9, the phases F0–F2, the checks P2–P8 and the adapter doc's A1–A10.
"""
from __future__ import annotations

import ast
import re
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


#: the shapes of an internal note's id; a public reference is allowed by name (`adapter doc A5`, I1–I9, F0–F2, P2–P8)
REVIEW_ID = re.compile(r"\b(review \d|round \d|MINOR ?\d+|MAJOR ?\d+|BLOCKER|NM-?\d+|PA-\d+|PB-\d+|TA-\d+|R3-B1|MJ\d"
                       r"|§\d+(\.\d+)?|[MBNCDE]\d{1,2})\b|plan §|audit [A-Z]\d|(?<!adapter doc )\bA\d{1,2}\b")


def test_no_comment_or_docstring_cites_an_internal_review_id():
    found = [f"{p.relative_to(ENGINE)}:{n}: {m.group(0)}" for p in sorted(PKG.rglob("*.py"))
             for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
             for m in [REVIEW_ID.search(line)] if m]
    assert not found, "\n".join(found)

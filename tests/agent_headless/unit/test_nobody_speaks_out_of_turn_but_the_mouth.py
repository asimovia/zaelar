"""ONE mouth speaks: `nucleo/pulse/notices.notify` out of a turn (V2-851 F2, node 2.1071), the turn's own reply in it.

`voice/proactive.notify` is the speaking primitive under it. Before F2, 33 callers reached the primitive directly —
a task's line with no `task_id`, a notice with no key, no ledger, no dedupe — and the battery measured 9.7–14.2 % of
turns speaking again after their reply. This test reads the product's source: a direct call of the primitive outside
the list below is a new mouth. The list only goes DOWN; each entry names the phase that removes it. V2-851 F5 took off
the last five: the in-turn three, the fast lane's chat-only line and the composed-document line go through
`nucleo/turn/mouth.say` — the turn's verdict while it is live, else `notices.notify` with a key.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCAN = ("nucleo", "voice", "widgets", "connectors", "server", "memory", "bus")

#: file → why it may still call the primitive. Only goes down.
ALLOWED = {
    "nucleo/pulse/notices.py": "the out-of-turn mouth itself: its voice leg",
}


def _calls_the_primitive(tree: ast.AST) -> bool:
    imported_notify = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "voice.proactive" \
                and any(a.name == "notify" for a in node.names):
            imported_notify = True
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "notify" and isinstance(f.value, ast.Name) \
                    and f.value.id in ("proactive", "_proactive", "_pro"):
                return True
    return imported_notify


def offenders(allowed: dict) -> list[str]:
    out = []
    for top in SCAN:
        for p in (ROOT / top).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel in allowed or "/_user/" in rel:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            if _calls_the_primitive(tree):
                out.append(rel)
    return sorted(out)


def test_only_the_mouth_calls_the_speaking_primitive():
    assert offenders(ALLOWED) == [], "a line out of turn goes through `nucleo/pulse/notices.notify` with its identity"


def test_the_allowed_list_has_no_dead_entry():
    dead = [f for f in ALLOWED if not (ROOT / f).exists()
            or not _calls_the_primitive(ast.parse((ROOT / f).read_text(encoding="utf-8")))]
    assert dead == [], f"an entry that no longer calls the primitive comes off the list: {dead}"


def test_disarm_the_scan_sees_a_direct_call():
    tree = ast.parse("async def f():\n    from voice import proactive\n    await proactive.notify('x', 'y')\n")
    assert _calls_the_primitive(tree)
    tree = ast.parse("from voice.proactive import notify\n")
    assert _calls_the_primitive(tree)
    assert offenders({}) == ["nucleo/pulse/notices.py"], "dropping the door's own entry makes its file an offender"


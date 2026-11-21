"""Only `nucleo/queue` writes the queue's rows (INI-078, Q-4), and the other writers of the task table only go away.

Read off the product's own source. The queue's store doors (`queue_insert`, `queue_archive`) are called from
`nucleo/queue` alone. The generic writers (`task_put`, `task_patch`) are still called by the files below for the rows
that are not tasks of the queue — crons, event flows, inline rows, questions — and by today's worker writers, which
move to signals lane by lane: the list is a ceiling that only drops. A file that stops calling them leaves the list in
the same commit; a new one is refused.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
QUEUE = "nucleo/queue/"
STORE = "memory/"
_SKIP = {".venv", "tests", "node_modules", "__pycache__", ".git", ".meshkore", ".claude", "TMP"}
GENERIC = {"task_put", "task_patch"}
OWN = {"queue_insert", "queue_archive"}
#: who still calls the generic writers outside the queue — only drops (2026-11-21, step 2 of the orchestrator)
WRITERS = frozenset({
    "nucleo/circuit/__init__.py", "nucleo/circuit/asker.py", "nucleo/circuit/ledger.py", "nucleo/circuit/waits.py",
    "nucleo/events/stream.py", "nucleo/mesh_jobs.py", "nucleo/request/answered_task.py",
    "nucleo/request/ask_outside_door.py", "nucleo/request/consent_ask.py", "nucleo/request/inline_ask.py",
    "nucleo/request/model.py", "nucleo/request/order_unserved.py", "nucleo/workers/prompts/playbook.py",
    "nucleo/workers/relay.py", "nucleo/workers/session_events.py", "nucleo/workers/session_finish.py",
})


def _calls() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if set(Path(rel).parts) & _SKIP or rel.startswith(STORE):
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8", errors="replace"))):
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if name in GENERIC | OWN:
                    out.setdefault(rel, set()).add(name)
    return out


def test_the_queues_own_writers_are_called_from_the_queue_alone():
    calls = _calls()
    assert [f for f, names in calls.items() if names & OWN and not f.startswith(QUEUE)] == []
    assert any(f.startswith(QUEUE) for f, names in calls.items() if names & OWN), "the queue writes through them"


def test_the_other_writers_of_the_task_table_only_go_away():
    outside = {f for f, names in _calls().items() if names & GENERIC and not f.startswith(QUEUE)}
    assert outside <= WRITERS, f"a new writer of the task table: {sorted(outside - WRITERS)} — send a signal instead"
    assert WRITERS <= outside, f"no longer a writer, take it off the list: {sorted(WRITERS - outside)}"

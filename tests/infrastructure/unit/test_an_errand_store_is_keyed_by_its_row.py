"""No errand-scoped store is keyed by the bare task id — the per-boot counter (V2-868 D1, shape of node 2.898).

Measured on the operator's console: the research brief lived under `research_brief:<task_id>` in the memory KV, which
survives restarts, while `task_id` restarts at 1 every boot. The first errand after a boot read the previous boot's
first errand's brief (a podcast research), was judged against it and relaunched with it. V2-288 (the workdir) and
V2-259 (the sheet) had closed the same class one store at a time; this walks the product tree so the next store
keyed that way goes red with its file and line:

  · a memory KV key (`kv_set`/`kv_get`/`kv_delete`) built from a bare task id — `f"…:{task_id}"`, `{tid}`, `{key}`,
    `{rec.task_id}` — is refused: compose it through `runtime_ids.errand_key`;
  · a brief written or read (`save`/`load`/`read` on `nucleo.workers.brief` or `brief_store`, however imported) with
    a bare task id is refused: hand it the record, or the row id.

Disarm: `test_the_walker_catches_the_measured_shape` feeds the walker the line the brief store had before V2-868.
"""
from __future__ import annotations

import ast
import pathlib

ENGINE = pathlib.Path(__file__).resolve().parents[3]
_ROOTS = ("nucleo", "voice", "widgets", "server", "memory", "connectors", "search", "rules")
_SKIP = {".venv", "node_modules", "vendor", ".git", "tests", "__pycache__", ".claude", ".meshkore", "_data", "_user"}
#: The names a bare per-boot task id goes by in the product.
_BARE = {"task_id", "tid", "key"}
_KV = {"kv_set", "kv_get", "kv_delete", "kv_del"}
_BRIEF_OPS = {"save", "load", "read"}
_BRIEF_MODULES = {"nucleo.workers.brief", "nucleo.workers.brief_store"}


def _bare(node) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _BARE
    if isinstance(node, ast.Attribute):
        return node.attr == "task_id"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str" and node.args:
        return _bare(node.args[0])
    return False


def _brief_names(tree) -> set[str]:
    """The local names this file binds to the brief modules, plus the dispatcher's `research` alias."""
    out = {"research"}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                if f"{n.module}.{a.name}" in _BRIEF_MODULES:
                    out.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name in _BRIEF_MODULES and a.asname:
                    out.add(a.asname)
    return out


def _receiver(func) -> str:
    v = func.value if isinstance(func, ast.Attribute) else None
    return v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else ""


def offenders(source: str, where: str = "<src>") -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    briefs, out = _brief_names(tree), []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.args):
            continue
        arg = n.args[0]
        if n.func.attr in _KV and isinstance(arg, ast.JoinedStr):
            if any(isinstance(v, ast.FormattedValue) and _bare(v.value) for v in arg.values):
                out.append(f"{where}:{n.lineno} {n.func.attr} keyed by a bare task id")
        elif n.func.attr in _BRIEF_OPS and _receiver(n.func) in briefs and _bare(arg):
            out.append(f"{where}:{n.lineno} brief {n.func.attr} by a bare task id")
    return out


def _tree():
    for root in _ROOTS:
        for p in sorted((ENGINE / root).rglob("*.py")):
            if not _SKIP.intersection(p.relative_to(ENGINE).parts):
                yield p


def test_no_errand_store_is_keyed_by_the_bare_task_id():
    bad = [o for p in _tree() for o in offenders(p.read_text(encoding="utf-8"), str(p.relative_to(ENGINE)))]
    assert not bad, "compose the key through `runtime_ids.errand_key` (the row id, else boot-stamped):\n" + "\n".join(bad)


def test_the_brief_store_keys_through_the_door():
    src = (ENGINE / "nucleo" / "workers" / "brief_store.py").read_text(encoding="utf-8")
    keys = [n.args[0] for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _KV]
    briefs = [k for k in keys if not (isinstance(k, ast.Name) and k.id == "_KV_ROUND")]   # rounds: by objective
    assert briefs and all(isinstance(k, ast.Call) and getattr(k.func, "id", "") == "_key" for k in briefs)
    assert "errand_key" in src


def test_the_walker_catches_the_measured_shape():
    before = ('from memory import api as memory\n'
              'def save(task_id, brief):\n    memory.kv_set(f"{_b._KV}:{task_id}", brief)\n'
              'def load(rec):\n    return memory.kv_get(f"research_brief:{rec.task_id}")\n')
    assert len(offenders(before)) == 2
    callers = ('from nucleo.workers import brief as _brief\n'
               'def f(rec, key):\n    _brief.save(key, {})\n    _d.research.load(str(rec.task_id))\n'
               '    _brief.save(rec, {})\n    other.save(key, {})\n')
    assert [o.split(" ", 1)[1] for o in offenders(callers)] == ["brief save by a bare task id",
                                                                 "brief load by a bare task id"]

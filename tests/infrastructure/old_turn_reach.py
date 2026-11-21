"""The old turn's reach (INI-078 F2 step 8, T0): which pieces of `nucleo/turn` and `nucleo/flash` something LIVE still
needs, and which nothing live reaches.

The live roots are the conversation manager's host, the events, the tasks, the send owner, the widgets, the connectors,
the rules, the memory and the server; the walk follows every import (the lazy ones inside functions and the dotted
names written as strings for `__import__`) and never walks INTO the old path — the old turn's pipeline, Flash's router
and executor, the old tool catalogue, the old voice provider — so a piece only those reach is not counted as needed.
What it prints: each old module a live root reaches, with the chain that reaches it; and the old modules nothing live
reaches (the ones a removal may take).

    ./.venv/bin/python tests/infrastructure/old_turn_reach.py            # reached, with their chains
    ./.venv/bin/python tests/infrastructure/old_turn_reach.py --unreached
"""
from __future__ import annotations

import ast
import collections
import re
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
OLD = ("nucleo.turn", "nucleo.flash")
#: the old path that is not under those two folders: walked into, never through
OLD_ELSEWHERE = ("voice.engine.llm.providers.nucleo", "voice.engine.llm.providers.attention_turn",
                 "voice.engine.llm.providers.flow_lifecycle", "voice.engine.llm.providers.fast_lane",
                 "voice.engine.pipeline.eager_brief", "nucleo.acts.tools", "nucleo.acts.card_")
#: the live roots (the move map's §7.1): every module under these prefixes
ROOTS = ("nucleo.conversation_host", "conversation", "nucleo.actionmap", "nucleo.events", "nucleo.pulse",
         "nucleo.errands", "nucleo.dispatch", "nucleo.workers", "nucleo.circuit", "nucleo.send", "widgets",
         "connectors", "rules", "memory", "server")
_DOTTED = re.compile(r"(nucleo|voice|conversation|widgets|connectors|memory|server|i18n|genome|search|a2a|rules|bus|"
                     r"config|observability)(\.\w+)+")


def _path(mod: str) -> Path | None:
    p = ENGINE / mod.replace(".", "/")
    for c in (p.with_suffix(".py"), p / "__init__.py"):
        if c.exists():
            return c
    return None


def _module(rel: str) -> str:
    return rel[:-3].replace("/", ".").removesuffix(".__init__")


def imports(path: Path, mod: str) -> set[str]:
    """Every module this file names: imports anywhere in it, and dotted names written as strings."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    pkg = mod if path.name == "__init__.py" else mod.rpartition(".")[0]
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = pkg.split(".")[: len(pkg.split(".")) - (n.level - 1)] if n.level > 1 else pkg.split(".")
                base = ".".join(parts + ([base] if base else []))
            out.add(base)
            out.update(f"{base}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and _DOTTED.fullmatch(n.value):
            out.add(n.value)
    return {m for m in out if _path(m)}


def _old(mod: str) -> bool:
    return mod.startswith(OLD) or mod.startswith(OLD_ELSEWHERE)


def _tracked() -> list[str]:
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return [f for f in files if not f.startswith("tests/") and "/tests/" not in f]


def reach() -> dict[str, str]:
    """Old module → the live module that first reaches it (a breadth-first walk from the roots)."""
    seeds = [_module(f) for f in _tracked() if _module(f).startswith(ROOTS)]
    seen: dict[str, str | None] = {s: None for s in seeds}
    queue = collections.deque(seeds)
    while queue:
        mod = queue.popleft()
        path = _path(mod)
        if path is None or _old(mod):
            continue                                    # the old path is reached, never walked through
        for dep in imports(path, mod):
            if dep not in seen:
                seen[dep] = mod
                queue.append(dep)
    return {m: str(p) for m, p in seen.items() if _old(m) and p is not None}


def old_modules() -> list[str]:
    return sorted(_module(f) for f in _tracked() if _module(f).startswith(OLD))


if __name__ == "__main__":
    reached = reach()
    if "--unreached" in sys.argv:
        for m in old_modules():
            if m not in reached and not m.endswith(("nucleo.turn", "nucleo.flash")):
                print(m)
    else:
        for m in sorted(reached):
            print(f"{m}  <-  {reached[m]}")
        print(f"\n{len(reached)} old modules reached by a live root; {len(old_modules())} old modules in all")


# ── by FUNCTION (the move map §7.1 (1)): which functions a live root REACHES call a reader of the old brief ──────────
def _functions(mod: str) -> dict:
    """`{qualified name: (node, local names → (module, attr) or module)}` for a module's functions and methods."""
    path = _path(mod)
    if path is None:
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return {}
    pkg = mod if path.name == "__init__.py" else mod.rpartition(".")[0]

    def names(node) -> dict:
        out = {}
        for n in ast.walk(node):
            if isinstance(n, (ast.Assign, ast.NamedExpr)) and (m := _imported(n.value)):      # x = __import__("m", …)
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Name):
                        out[t.id] = m
            elif isinstance(n, ast.Import):
                for a in n.names:
                    out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    parts = pkg.split(".")
                    parts = parts[: len(parts) - (n.level - 1)] if n.level > 1 else parts
                    base = ".".join(parts + ([base] if base else []))
                for a in n.names:
                    full = f"{base}.{a.name}"
                    out[a.asname or a.name] = full if _path(full) else (base, a.name)
        return out
    top = names(tree)
    out = {}
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[n.name] = (n, {**top, **names(n)})
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{n.name}.{m.name}"] = (m, {**top, **names(m)})
    return out


def _imported(node) -> str:
    """The module a `__import__("<module>", …)` names, when it is one of ours; else ""."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__" and node.args \
            and isinstance(node.args[0], ast.Constant) and _path(str(node.args[0].value)):
        return str(node.args[0].value)
    return ""


def _calls(mod: str, fn, local: dict, own: dict) -> set:
    """`(module, function)` this function calls: a name of its own module, a from-imported function, or
    `<module alias>.<function>`."""
    out = set()
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name):
            if f.id in own:
                out.add((mod, f.id))
            elif isinstance(local.get(f.id), tuple):
                out.add(local[f.id])
        elif isinstance(f, ast.Attribute) and _imported(f.value):
            out.add((_imported(f.value), f.attr))
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.NamedExpr) and _imported(f.value.value):
            out.add((_imported(f.value.value), f.attr))
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            target = local.get(f.value.id)
            if isinstance(target, str):
                out.add((target, f.attr))
            elif f.value.id == "self":
                cls = next((k.split(".")[0] for k in own if "." in k), "")
                out.add((mod, f"{cls}.{f.attr}") if cls else (mod, f.attr))
    return out


def reaching(roots: tuple, targets: tuple) -> dict:
    """`{(live function, target function it calls): the chain from a root}` — walking calls from every function of the
    roots' modules, never INTO the old path; every live caller of a target module's function is named."""
    cache: dict = {}

    def funcs(mod):
        if mod not in cache:
            cache[mod] = _functions(mod)
        return cache[mod]
    start = [(m, f) for rel in _tracked() for m in [_module(rel)] if m.startswith(roots) for f in funcs(m)]
    seen = {s: None for s in start}
    queue = collections.deque(start)
    hits = {}
    while queue:
        mod, name = queue.popleft()
        if _old(mod):
            continue
        got = funcs(mod).get(name)
        if got is None:
            continue
        fn, local = got
        for callee in _calls(mod, fn, local, funcs(mod)):
            if callee[0].startswith(targets):            # a live function that reads the target: named by ITS caller
                chain, p = [f"{mod}.{name}"], seen[(mod, name)]
                while p is not None and len(chain) < 12:
                    chain.append(f"{p[0]}.{p[1]}")
                    p = seen[p]
                hits.setdefault((f"{mod}.{name}", f"{callee[0]}.{callee[1]}"), chain)
            elif callee not in seen:
                seen[callee] = (mod, name)
                queue.append(callee)
    return hits

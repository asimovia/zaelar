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

"""Nothing outside the old turn imports it, and that only ever falls (INI-078 F2 step 8, the move map §7.4).

The old turn (`nucleo/turn/`, `nucleo/flash/`) is being removed: what something live still needs MOVES to the module
that owns it, a reading of the old brief is CUT, the rest is deleted. This ratchet counts every place outside those two
folders (and outside `tests/`) that names one of their modules — an import anywhere in a file, the lazy ones inside a
function included, and a dotted name written as a string for `__import__` — and holds the count at its ceiling. Each
batch of the move lowers the ceiling in the same commit; it never rises. At zero the two folders must be gone.

Which old pieces something live still reaches, and which nothing does: `tests/infrastructure/old_turn_reach.py`.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
OLD = ("nucleo.turn", "nucleo.flash")
#: measured 2026-11-21 at main 860a7b8da (T0: 330); only lowered, in the commit that removes the imports — T1: 313, T2: 291, T3: 283, T4: 263, E7d-3: 262, T6–T8: 216, the brief cut: 213, the unplug: 208, L1 B2: 182, L1 B3: 167, L1 B4: 151
CEILING = 151
_NAMED = re.compile(r"nucleo\.(turn|flash)(\.\w+)*")


def _names_old(name: str) -> bool:
    return name == OLD[0] or name == OLD[1] or name.startswith(tuple(o + "." for o in OLD))


def count_in(text: str) -> int:
    """How many times this source names an old module: one per import statement's module or imported name that is one,
    and one per string literal that is one."""
    tree = ast.parse(text)
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            n += sum(1 for a in node.names if _names_old(a.name))
        elif isinstance(node, ast.ImportFrom) and not node.level:
            mod = node.module or ""
            if _names_old(mod):
                n += 1
            elif mod == "nucleo":
                n += sum(1 for a in node.names if a.name in ("turn", "flash"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and _NAMED.fullmatch(node.value):
            n += 1
    return n


def _counts() -> dict[str, int]:
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    out = {}
    for rel in files:
        if rel.startswith(("tests/", "nucleo/turn/", "nucleo/flash/")) or "/tests/" in rel:
            continue
        path = ENGINE / rel
        if not path.exists():
            continue
        try:
            n = count_in(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        if n:
            out[rel] = n
    return out


def test_what_names_the_old_turn_from_outside_only_falls():
    counts = _counts()
    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
    assert total <= CEILING, (f"{total} places outside the old turn name it (ceiling {CEILING}): a new one was added — "
                              f"call the module that owns the piece instead. Most: {top}")
    if CEILING == 0:
        assert not any((ENGINE / d).exists() for d in ("nucleo/turn", "nucleo/flash")), "at zero the old turn is gone"


def test_the_counter_sees_every_way_of_naming_it():
    src = ("import nucleo.turn.brief\nfrom nucleo.flash import data_ops, dialog\nfrom nucleo import turn\n"
           "def f():\n    from nucleo.turn.prompt import catalogs\n    return __import__('nucleo.flash.router')\n"
           "from nucleo.acts import canvas\nfrom . import turn\n")
    assert count_in(src) == 5

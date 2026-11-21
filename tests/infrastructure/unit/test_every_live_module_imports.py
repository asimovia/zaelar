"""Every live module of the product IMPORTS — not only resolves (INI-078 L1, B0).

`test_every_import_names_a_module_that_exists` reads each import statement and resolves its target. That does not run
a module's top level: a module whose own body fails (a name it imports at module level that a deletion took away, an
attribute read while the module is half built) passes it and breaks at run time — the first time the engine reaches
it. Deleting the old turn removes ~150 modules at once, so this imports every live one, for real.

One process imports them all, in path order. A failure there is either a real break (red) or an ORDER artefact: a
module whose package imports its parts and whose parts import the package back fails when a part is reached first.
Such a module is imported again in a fresh process; it passes there, or it is declared debt below and only shrinks.

Disarm: add `from nucleo.no_such_module import x` to the top of `nucleo/whisper/run.py` — the sweep names it
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[3]

#: The engine's own top-level packages.
_OURS = ("nucleo", "voice", "widgets", "server", "memory", "connectors", "search", "rules", "i18n", "bus",
         "observability", "config", "files", "library", "update", "conversation", "genome", "a2a")

#: Modules that cannot be imported FIRST, on their own: a package and its parts import each other, and the part
#: reached first finds the package half built. Measured 2026-11-21; each is debt, the list only shrinks — a module
#: that imports cleanly on its own leaves it in the same commit.
KNOWN_ORDER_CYCLES = {
    "connectors.telegram.account_ops", "nucleo.acts.act_policy", "nucleo.acts.card_verdict",
    "widgets.agenda.actions", "widgets.archivos.actions", "widgets.archivos.cloud", "widgets.contactos.actions",
    "widgets.documento.actions", "widgets.mensajeria.actions", "widgets.mensajeria.actions.fetch",
    "widgets.mensajeria.actions.groups", "widgets.mensajeria.actions.leave", "widgets.mensajeria.actions.open",
    "widgets.mensajeria.actions.send", "widgets.musica.actions", "widgets.results.actions",
    "widgets.youtube.actions", "widgets.youtube.blocking",
}

_SWEEP = r"""
import importlib, json, sys
sys.path.insert(0, ".")
bad = {}
for m in json.loads(sys.argv[1]):
    try:
        importlib.import_module(m)
    except BaseException as e:  # noqa: BLE001 — every failure is reported by name
        bad[m] = f"{type(e).__name__}: {e}"[:300]
print("@@" + json.dumps(bad))
"""


def _live_modules() -> list[str]:
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    mods = []
    for f in files:
        if f.split("/")[0] not in _OURS or "/tests/" in f or f.endswith("__main__.py") or "/_user/" in f \
                or "/vendor/" in f or not (ENGINE / f).exists():
            continue
        m = f[:-3].replace("/", ".")
        mods.append(m[:-len(".__init__")] if m.endswith(".__init__") else m)
    return sorted(mods)


def _import(mods: list[str]) -> dict[str, str]:
    out = subprocess.run([sys.executable, "-c", _SWEEP, json.dumps(mods)], cwd=ENGINE, capture_output=True,
                         text=True, timeout=300)
    line = next((ln for ln in out.stdout.splitlines() if ln.startswith("@@")), None)
    assert line is not None, f"the import sweep did not finish: {out.stderr[-2000:]}"
    return json.loads(line[2:])


def _alone(m: str) -> str:
    """The failure of importing `m` first in a fresh process (after its top package), or ""."""
    return _import([m.split(".")[0], m]).get(m, "")


def test_every_live_module_imports():
    bad = _import(_live_modules())
    broken = {m: e for m, e in bad.items() if "partially initialized module" not in e}
    assert not broken, f"live modules that do not import: {broken}"
    order = {m: _alone(m) for m in bad if m not in broken and m not in KNOWN_ORDER_CYCLES}
    assert not {m: e for m, e in order.items() if e}, f"a module that cannot be imported on its own, new: {order}"


def test_the_order_cycles_only_shrink():
    clean = sorted(m for m in KNOWN_ORDER_CYCLES if not _alone(m))
    assert not clean, f"these import on their own now — take them out of KNOWN_ORDER_CYCLES: {clean}"

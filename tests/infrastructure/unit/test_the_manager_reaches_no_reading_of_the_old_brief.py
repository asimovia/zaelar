"""Nothing the conversation manager reaches reads the old turn's brief (INI-078 F2, before the unplug).

After the unplug the old turn never runs, so its brief is always empty: a live function that fetched it would decide on
nothing, silently. Walked by FUNCTION, not by module (`old_turn_reach.reaching`): from every function of
`conversation/` and `nucleo/conversation_host/`, through the calls each makes — never into the old turn — no function
may call a SOURCE of the brief: a function of `nucleo.turn.brief*` or `nucleo.turn.verdicts` that obtains the turn's
brief on its own (its first parameter is no handle it was handed). A pure reader of a handle a caller passed is no
source: on the manager's path that handle is None, which is the caller's own guard.

What the old turn decided and a shared door still wants comes through the request's record instead: the turn that
began the request hands its verdicts' reader (`request.model.begin(brief=…)`, read by `model.verdicts()`); the
manager hands none, and hands what it has itself (his words to the stop door, the model's call to the errand).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ENGINE / "tests" / "infrastructure"))
import old_turn_reach as reach  # noqa: E402

ROOTS = ("nucleo.conversation_host", "conversation")
BRIEF = ("nucleo.turn.brief", "nucleo.turn.verdicts")
HANDLES = ("handle", "brief")
#: sources the manager may still reach, each with why it reads nothing empty (INI-078 F5 cut the errand's): none left
ALLOWED: frozenset = frozenset()


def _sources() -> set[str]:
    """`module.function` of every function in the brief modules that is not handed a brief handle first."""
    out = set()
    for mod in sorted({m for rel in reach._tracked() for m in [reach._module(rel)] if m.startswith(BRIEF)}):
        for name, (fn, _local) in reach._functions(mod).items():
            first = [a.arg for a in fn.args.posonlyargs + fn.args.args if a.arg != "self"][:1]
            if not first or first[0] not in HANDLES:
                out.add(f"{mod}.{name}")
    return out


def _defined(target: str) -> str:
    """Where `module.function` is defined: a name a brief module re-exports (`brief.of_this_turn`) is followed to the
    module that defines it."""
    for _ in range(4):
        mod, _, name = target.rpartition(".")
        if name in reach._functions(mod) or not reach._path(mod):
            return target
        tree = ast.parse(reach._path(mod).read_text(encoding="utf-8"))
        src = next((n.module for n in tree.body if isinstance(n, ast.ImportFrom) and n.module
                    and any((a.asname or a.name) == name for a in n.names)), None)
        if not src:
            return target
        target = f"{src}.{name}"
    return target


def _fetches(hits: dict) -> dict:
    sources = _sources()
    return {(caller, target): chain for (caller, target), chain in hits.items()
            if _defined(target) in sources and caller not in ALLOWED}


def test_no_function_the_manager_reaches_fetches_the_old_brief():
    assert "nucleo.turn.brief_turn.of_this_turn" in _sources(), "the walk lost the brief's own source"
    assert _defined("nucleo.turn.brief.of_this_turn") == "nucleo.turn.brief_turn.of_this_turn"
    got = _fetches(reach.reaching(ROOTS, BRIEF))
    assert not got, "a live function the manager reaches fetches the old brief — it is empty after the unplug:\n" + \
        "\n".join(f"  {t} ← " + " ← ".join(c[:6]) for (_, t), c in sorted(got.items()))


def test_disarm_a_fetch_of_the_brief_on_the_widget_door_is_named():
    path = ENGINE / "nucleo/request/ending.py"
    text = path.read_text(encoding="utf-8")
    cut = "    turn = model.current()\n    how, leaves = \"\", False\n"
    assert cut in text
    armed = text.replace(cut, cut + "    from nucleo.turn import brief as _tb\n    _tb.of_this_turn()\n")
    try:
        path.write_text(armed, encoding="utf-8")
        got = _fetches(reach.reaching(ROOTS, BRIEF))
        assert ("nucleo.request.ending.hold", "nucleo.turn.brief.of_this_turn") in got, sorted(got)
    finally:
        path.write_text(text, encoding="utf-8")

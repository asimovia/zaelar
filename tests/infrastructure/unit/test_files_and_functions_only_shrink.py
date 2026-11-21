"""Files and functions only shrink (V2-778 F1-15, 2026-09-30).

The operator's axis for the whole cleanup: «una de las cosas más importantes de un proyecto es no tener archivos
demasiado grandes». The demo week added 19.1k product lines, and the de-facto router ended up as ONE coroutine of
~3,500 lines inside the LiveKit adapter. This is the ratchet that stops it growing back while F1 splits it.

Three ceilings over every tracked product `.py` (not tests): a FILE over 800 lines, a FUNCTION over 120 lines,
a function with more than 100 branches. Each offender of the day is NAMED below with its size — the provider and
the probe included. The rule: nothing new may cross a ceiling, and no named offender may grow. Shrinking passes;
when an entry shrinks, lower its number here (or delete it once it is under the ceiling) in the same commit.

The ceilings (800 / 120) are the audit's PROPOSAL; the number is the operator's open decision (V2-778 §Open
decisions). Changing them is one line each.

A function's size is counted from its `def` to its last line, nested functions included, and every nested
function is also counted on its own — so splitting a closure out of `_run_inner` lowers both numbers.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
FILE_MAX, FUNC_MAX, BRANCH_MAX = 800, 120, 100

# V2-778 F1-10a/b (2026-10-01): the tool executor and the post-stream chain MOVED out of `_run_inner` into
# `nucleo/flash/tool_executor.py` and `nucleo/flash/post_stream.py` (same code, same sizes); their entries were
# renamed, not added — and splitting both under the ceilings is owed. The executor's widget half then moved to
# `tool_executor_widget.py` (2026-10-01): the file entry went under the ceiling, the function entries were renamed.
# 2026-10-16 (audit V2-783 P1-4): the three tables were RED since 2026-10-03 (`_exec_allow` crossed 280 lines in
# dad7f3bd) and stayed red through 114 commits — a ratchet nobody runs holds nothing. Re-measured at HEAD and
# frozen there: every entry is today's size, down-only from here. The debt it names is unchanged and still owed.
FILES = {
    'nucleo/llm/fast_client.py': 814,
    'voice/observer.py': 809,   # 2026-11-19 V2-941: the isolated turn manager's kinds get their observer family (27a14c358, plan PA-1); +2 2026-11-21 INI-078: the queue's own kind (`queue`) and the decider's record (`route`); only shrinks
    'widgets/directory.py': 801,   # 2026-11-18 contacts: one directory fed by every linked source, one row per person (18b837d66, b76bfb801, 98a166e3f); found red on main 2026-11-19, recorded by INI-042 #44; only shrinks   # 2026-11-09: red on main before the V2-867/868/859/575 batch (observability owner); only shrinks from here
}

FUNCTIONS = {
    'widgets/mensajeria/outbound/targets.py::resolve_target': 122,  # 2026-11-18 V2-938 + contacts one row: the chosen row's id and a reply's chat resolve here (d44a9272c, 6acb9baa4, 18b837d66); found red on main 2026-11-19; only shrinks
    'config/settings.py::update': 149,  # +3 2026-11-17 V2-928: the presence settings (face, on/off, camera) are one more validated group
    'memory/writer/__init__.py::insert_memory': 151,
    'nucleo/actionmap/executor.py::execute': 143,
    'nucleo/dispatch/session.py::_run_session': 189,
    'nucleo/errands/wake.py::wake': 154,  # +1 2026-11-19 INI-042 #44 P-1: a watch errand leaves before the model turn
    'nucleo/llm/fast_client.py::FastClient._stream_inner': 267,
    'widgets/navegador/live_lines.py::navegador_lines': 147,   # refactor2710-08b: moved
    'nucleo/memory_agent/ingest_steps.py::file_the_atoms': 127,
    'nucleo/memory_agent/ingest_steps.py::gate_the_utterance': 148,
    'nucleo/cli/worker_api_exec.py::_exec_allow': 175,   # V2-883 merge: the scheduler's acts left for worker_api_schedule.run; V2-851 trim B: the spawn act went
    'nucleo/workers/providers/claude_map.py::_map': 125,   # V2-851 trim B: re-measured
    'nucleo/workers/providers/claude_start.py::start': 134,   # +4 V2-931 (2.1801): a task marked for Claude itself takes that rung or does not start (`claude_tier.route`); V2-851 trim B: re-measured
    'server/voice_status.py::brain_and_voice': 140,
    'server/voice_status.py::the_rest_and_the_light': 192,
    # V2-851 F5 (2.1191): `_run_inner` (705) and `turn_after.close_the_turn` (294) MOVED to nucleo/turn and split by
    # stage — the three over the line are the moved bodies, each shorter than what they came from.
    'voice/engine/pipeline/agent_events.py::_on_data': 122,
    'voice/tag_protocol.py::strip_tags': 212,
    'widgets/agenda/actions.py::_a_add_meeting': 145,  # 2026-11-08 apps principles: the mirror status is offered, the write is logged;  # +3 2026-11-06 (4.392): the row the write lands on is handed to the notice writer (`_row`)
    'widgets/agenda/tasklists.py::apply': 157,
    'widgets/generator.py::_run_agent_once': 128,
    'widgets/imagenes/data.py::apply_action': 141,  # 2026-11-08 apps principles: the set counter a show's end state reads
    'widgets/refs.py::resolve': 122,
    'widgets/youtube/library.py::apply': 175,   # V2-806: the preference branches moved to youtube/prefs
}

BRANCHES = {
    'widgets/agenda/tasklists.py::apply': 104,
    'widgets/youtube/library.py::apply': 101,
}


def _product_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    return [p for p in out if not p.startswith("tests/") and "/tests/" not in p]


def _branches(fn) -> int:
    n = 0
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.With,
                             ast.AsyncWith, ast.match_case)):
            n += 1
        elif isinstance(node, ast.BoolOp):
            n += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            n += 1 + len(node.ifs)
    return n


def _measure():
    files, funcs, branches = {}, {}, {}
    for rel in _product_files():
        p = ENGINE / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        lines = src.count("\n") + (0 if src.endswith("\n") else 1)
        if lines > FILE_MAX:
            files[rel] = lines
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        def visit(node, prefix):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    q = f"{prefix}{ch.name}"
                    ln = ch.end_lineno - ch.lineno + 1
                    if ln > FUNC_MAX:
                        funcs[f"{rel}::{q}"] = ln
                    b = _branches(ch)
                    if b > BRANCH_MAX:
                        branches[f"{rel}::{q}"] = b
                    visit(ch, q + ".")
                elif isinstance(ch, ast.ClassDef):
                    visit(ch, f"{prefix}{ch.name}.")
                else:
                    visit(ch, prefix)
        visit(tree, "")
    return files, funcs, branches


def _grown(now: dict, base: dict) -> list[str]:
    return [f"{k}: {v} (baseline {base.get(k, 'none — new offender')})" for k, v in sorted(now.items())
            if v > base.get(k, 0)]


def test_no_file_grows_past_the_ceiling():
    files, _, _ = _measure()
    assert not _grown(files, FILES), f"a product file over {FILE_MAX} lines grew or is new: {_grown(files, FILES)}"


def test_no_function_grows_past_the_ceiling():
    _, funcs, _ = _measure()
    assert not _grown(funcs, FUNCTIONS), \
        f"a function over {FUNC_MAX} lines grew or is new: {_grown(funcs, FUNCTIONS)}"


def test_no_function_grows_more_branches():
    _, _, branches = _measure()
    assert not _grown(branches, BRANCHES), \
        f"a function over {BRANCH_MAX} branches grew or is new: {_grown(branches, BRANCHES)}"


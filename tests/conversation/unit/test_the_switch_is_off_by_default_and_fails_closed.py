"""The switch: off by default, read once, failing closed (node 13.37, v3.1 B2).

Who decides, the first that says something: the session (`conv=1` / `conv=0`), the account (`conversation_manager`
in `config/settings.json`), the environment (`ZAELAR_CONVERSATION`). Switched on, a session goes by the manager only
with every outside write held, its language chosen and the manager's configuration passing; short of that it takes
the old path and says why. Off, nothing of the engine imports the host: every import of it is inside a function.
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

import pytest

from nucleo.conversation_host import switch

ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture
def clean(monkeypatch):
    for k in (switch.ENV, "ZAELAR_HOLD_OUTBOUND"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from config import settings
    monkeypatch.setattr(settings, "_read", lambda: {})
    return monkeypatch


def _account(monkeypatch, value) -> None:
    from config import settings
    monkeypatch.setattr(settings, "_read", lambda: {switch.SETTING: value})


def test_off_by_default(clean):
    assert switch.decide() == switch.Decision(False, "default")


def test_the_session_says_first_then_the_account_then_the_environment(clean):
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    clean.setenv(switch.ENV, "1")
    assert switch.decide() == switch.Decision(True, "env")
    _account(clean, False)
    assert switch.decide() == switch.Decision(False, "account")
    assert switch.decide("1") == switch.Decision(True, "session")
    _account(clean, True)
    assert switch.decide("0") == switch.Decision(False, "session")


@pytest.mark.parametrize("hold", ["", "errand,mandate"])
def test_switched_on_without_every_write_held_it_takes_the_old_path_and_says_why(clean, hold):
    if hold:
        clean.setenv("ZAELAR_HOLD_OUTBOUND", hold)
    got = switch.decide("1")
    assert not got.on and got.by == "session" and "ZAELAR_HOLD_OUTBOUND" in got.why


def test_switched_on_with_no_language_takes_the_old_path(clean):
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    clean.setenv("ZAELAR_LANGUAGE", "")
    got = switch.decide("1")
    assert not got.on and "language" in got.why


def test_a_configuration_out_of_order_is_refused(clean):
    import genome
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    g = json.loads(json.dumps(genome.genesis()))
    g["conversation"]["thresholds"]["complete_grace_ms"] = 4000          # «answerable» waiting longer than a mark
    clean.setattr(genome, "genesis", lambda: g)
    got = switch.decide("1")
    assert not got.on and "complete_grace_ms > terminal_grace_ms" in got.why


def _top_level_imports_of_the_host(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in tree.body:                              # module level only: an import inside a function is lazy
        names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        if any(n == "nucleo.conversation_host" or n.startswith("nucleo.conversation_host.") for n in names):
            lines.append(node.lineno)
    return lines


def test_off_nothing_of_the_engine_imports_the_host():
    skip = ("nucleo/conversation_host/", "tests/", ".venv/", "node_modules/")
    found = []
    for path in ENGINE.rglob("*.py"):
        rel = path.relative_to(ENGINE).as_posix()
        if rel.startswith(skip) or "/." in rel:
            continue
        found += [f"{rel}:{n}" for n in _top_level_imports_of_the_host(path)]
    assert not found, found


def test_the_proof_endpoint_reads_nothing_while_the_host_is_not_loaded(monkeypatch):
    from server import voice_api
    monkeypatch.delitem(sys.modules, "nucleo.conversation_host.proof", raising=False)
    got = json.loads(asyncio.run(voice_api.debug_conversation("s1")).body)
    assert got == {"session": "s1", "on": False}

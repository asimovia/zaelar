"""The manager is the only path, and it fails closed into silence (node 13.37, INI-078 F2: the unplug).

There is no mode and no old path: every session goes by the manager. It still runs only with every outside write held
but the lanes it carries, its language chosen and its configuration passing; short of that the session answers
nothing and the reason goes on his screen (`switch.silent`, an alert). Nothing of the engine imports the host at its
top: every import of it is inside a function.
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
    monkeypatch.delenv("ZAELAR_HOLD_OUTBOUND", raising=False)
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    return monkeypatch


def test_there_is_no_mode_every_session_goes_by_the_manager(clean):
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    for flag in (None, "0", "1", "text", False):
        got = switch.decide(flag)
        assert got.by == "manager" and (got.on or "configuration" in got.why)


@pytest.mark.parametrize("hold", ["", "errand,mandate", "all,-owner,-worker"])
def test_without_every_write_held_it_answers_nothing_and_says_why(clean, hold):
    if hold:
        clean.setenv("ZAELAR_HOLD_OUTBOUND", hold)
    got = switch.decide()
    assert not got.on and "ZAELAR_HOLD_OUTBOUND" in got.why


def test_with_no_language_it_answers_nothing(clean):
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    clean.setenv("ZAELAR_LANGUAGE", "")
    got = switch.decide()
    assert not got.on and "language" in got.why


def test_a_configuration_out_of_order_is_refused(clean):
    import genome
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all")
    g = json.loads(json.dumps(genome.genesis()))
    g["conversation"]["thresholds"]["complete_grace_ms"] = 4000          # «answerable» waiting longer than a mark
    clean.setattr(genome, "genesis", lambda: g)
    got = switch.decide()
    assert not got.on and "complete_grace_ms > terminal_grace_ms" in got.why


def test_a_session_it_may_not_take_is_silent_and_says_why_on_his_screen(clean):
    from types import SimpleNamespace

    from voice import observer
    alerts = []
    clean.setattr(observer, "emit", lambda kind, label, **kw: alerts.append((kind, kw.get("text"))))
    s = SimpleNamespace()
    switch.silent(s, "w_the reason")
    assert s._conversation_switch == switch.Decision(False, "refused", "w_the reason") and not switch.on(s)
    assert ("alert", "w_the reason") in alerts
    assert not hasattr(switch, "fall_back") and not hasattr(switch, "typed_on"), "nothing to fall back to"


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


def test_every_write_held_but_the_lanes_it_carries_is_enough(clean):
    """It sends by the owner's lane, each message with his yes (`declared.json` `sends_by`): `all,-owner` holds every
    other outside write — and only that one is let go."""
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all,-owner")
    from nucleo.conversation_host import switch as sw
    assert sw.refused() in ("", "no language chosen yet") or "configuration" in sw.refused()
    assert "holds too little" not in sw.refused()


def _too_little() -> bool:
    return "holds too little" in switch.refused()


def test_his_own_hand_is_a_lane_it_carries_and_no_other_lane_let_go_is(clean):
    """His Send on a card is his yes by gesture (`send/card.settle`): `all,-owner,-hand` lets the manager run; any other
    lane let go beside them leaves it silent, saying why."""
    from connectors import exit as _exit
    clean.setenv("ZAELAR_HOLD_OUTBOUND", "all,-owner,-hand")
    assert not _too_little()
    for lane in sorted(_exit.LANES - {"owner", "hand"}):
        clean.setenv("ZAELAR_HOLD_OUTBOUND", f"all,-owner,-hand,-{lane}")
        assert _too_little(), lane

"""I7: no code before the model picks a tool or the source of the answer, and nothing cuts the core tools (node 13.12).

Whatever the input — voice or text, Spanish or English tokens, a declared expectation (a number), a worker's result —
the model's call carries the whole catalog and every core tool in it (search, market data, discover tools), and no
tool runs before the model asked for it. Statically: the ear, the inbox and the composer name no tool of the catalog,
and the package holds no regex and no word table (counted the way the engine's own ratchet counts them).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conversation import envelopes as E
from conversation.ear import signals as S
from conversation.testing.fakes import catalog
from conversation.types import EnvelopeKind, WorkerUpdate
from tests.conversation.unit.convkit import Harness
from tests.infrastructure.unit import test_words_never_fix_a_case as words_ratchet

PKG = Path(__file__).resolve().parents[3] / "conversation"
CORE = {t.name for t in catalog() if t.core}


@pytest.mark.parametrize("how", ["voice", "text_es", "text_en", "expect_number", "worker"])
def test_the_model_call_carries_the_whole_catalog_and_no_tool_ran_before_it(store, how):
    h = Harness(store)
    if how == "voice":
        h.utter([(["w1", "w2"], 0)])
    elif how == "expect_number":
        h.hear(S.ContextHint("d1", "number"))
        h.utter([(["w3"], 0)], end_pause=1500)
        h.at(h.clock.mono + 5000).hear(S.Tick(h.clock.mono + 5000))
    elif how == "worker":
        h.conv.give(E.make(EnvelopeKind.WORKER_UPDATE, E.WorkerBody("t1", WorkerUpdate.RESULT, "w7"),
                           producer="worker:t1", producer_id="r1", account="acct-test", onset_ms=0, sealed_ms=0))
    else:
        h.typed({"text_es": "w4 w5", "text_en": "w6"}[how], h.clock.mono + 1)
        h.at(h.clock.mono + 1000)
    h.pump()
    assert h.model.calls, how
    for call in h.model.calls:
        names = [t.name for t in call.tools]
        assert CORE <= set(names) and names == [t.name for t in catalog()], how
    assert h.tools.calls == []


def _string_constants(path: Path) -> set[str]:
    return {n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_the_ear_the_inbox_and_the_composer_name_no_tool():
    tools = {t.name for t in catalog()} | {"web_search", "send", "reply_message", "show_widget"}
    named = [(p.relative_to(PKG).as_posix(), s) for d in ("ear", "inbox", "composer")
             for p in sorted((PKG / d).rglob("*.py")) for s in _string_constants(p) if s in tools]
    assert not named, named


def test_the_package_holds_no_regex_and_no_word_table():
    counts = {k: v for k, v in words_ratchet._counts().items() if k.startswith("conversation/") and v != (0, 0)}
    assert counts == {}, counts
    compiled = [p.name for p in PKG.rglob("*.py") if "re.compile" in p.read_text(encoding="utf-8")]
    assert compiled == []

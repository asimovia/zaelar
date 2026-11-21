"""A remark about the assistant is not a fact about him (node 13.149, C7).

His complaint about how the agent speaks («you are repeating yourself like a parrot») was filed in his memory as a fact.
The distiller decides what a turn leaves in memory; its own instructions now name a complaint or a comment about the
assistant — how it speaks, that it repeats itself, how it behaves — as something to discard, EXCEPT how he wants to be
treated from now on: that is `operator.treatment`, as its own example shows. A model double that obeys only what those
instructions say tells the one-off complaint (nothing stored) from the lasting treatment (its slot written), through
the real ingest.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import queue as memqueue
from nucleo import memory_agent
from nucleo.memory_agent.processor import distill, distill_config, distill_prompt

COMPLAINT = "w_you are repeating yourself like a parrot"
TREATMENT = "w_from now on talk to me informally and briefly"
EXCEPTION = "salvo cómo quiere que le trates desde ahora: es operator.treatment"


def _section(system: str) -> str:
    return system.split("LO QUE DICE DEL ASISTENTE", 1)[1].split("★", 1)[0]


def test_the_distiller_discards_what_he_says_about_the_assistant_but_his_treatment():
    rule = " ".join(_section(distill_prompt.messages("hola", {})[0]["content"]).split())
    assert "LO QUE DICE DEL ASISTENTE NO es un hecho de él" in distill_prompt.messages("hola", {})[0]["content"]
    assert "→ discard" in rule and EXCEPTION in rule
    assert '"slot":"operator.treatment"' in distill_prompt._FEWSHOT_ASSISTANT, "the example the exception points to"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")
    monkeypatch.setenv("MEMORY_RERANK", "off")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _obeying_double(monkeypatch):
    """A distiller double that does only what its instructions say about the assistant: a remark is discarded, and
    a lasting treatment goes to `operator.treatment` only when the instructions carve it out of the discard."""
    async def process(text, state=None):
        rule = " ".join(_section(distill_prompt.messages(text, state or {})[0]["content"]).split())
        if text == TREATMENT and EXCEPTION in rule:
            return [{"text": "Prefiere trato informal y breve.", "dest": "state", "kind": "pref", "importance": 0.8,
                     "ttl_days": None, "slot": "operator.treatment", "value": "informal y breve", "change": "none",
                     "concepts": [], "state_patch": {"treatment": "informal y breve"}}]
        return []
    monkeypatch.setattr(distill, "process", process)
    monkeypatch.setattr(distill_config, "enabled", lambda: True)


def _ingest(*utterances):
    async def scenario():
        await memapi.start()
        for u in utterances:
            await memory_agent.ingest_utterance(u, role="operator")
            await memqueue.get_queue().join()
        await memapi.stop()
    asyncio.run(scenario())


def test_a_one_off_complaint_leaves_nothing_and_a_lasting_treatment_writes_its_slot(fresh_db, monkeypatch):
    _obeying_double(monkeypatch)
    _ingest(COMPLAINT, TREATMENT)
    rows = memdb.get_db().query("SELECT text, slot FROM memories WHERE valid=1")
    assert [r["slot"] for r in rows if r["slot"] == "operator.treatment"], rows
    assert not [r for r in rows if "parrot" in str(r["text"]) or "repeating" in str(r["text"])], rows

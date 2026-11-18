"""An act that LEAVES crosses the one data-op gate, measured on the gate itself (refactor2710-06 T-02).

Behaviour, through `tests/widget_data_rig.py` — the gate runs whole and stops where an op starts or is held:

  · with a stranger's words in the context and no sure verdict, a reply is ASKED; without them it runs (CRIT-E12);
  · two readers disagree on an act that leaves → the verdict's act runs instead (full12 E3, node 2.106);
  · a sure ordered forward the model only drafted → the forward runs, to the person he named (live bench E3, 2.729);
  · a send to someone his words never named is asked, never sent (the operator, 2026-10-15).
"""
from __future__ import annotations

import pytest

from tests import widget_data_rig as rig


@pytest.fixture(autouse=True)
def _scene(tmp_path, monkeypatch):
    from nucleo import his_words, untrusted
    rig.scene(tmp_path, monkeypatch)
    yield
    untrusted.reset()
    his_words.reset()


def test_a_send_to_someone_his_words_never_named_is_never_sent_by_the_turn(tmp_path, monkeypatch):
    """Since V2-931 the turn hands a send over as ONE worker task and never runs or asks it itself; what keeps it from
    leaving is the worker's exit door (`nucleo/workers/exit_gate.leave`): a message is read off its declared risk and
    is asked, naming her, before anything leaves — never passed through on the turn's say-so."""
    import time
    from types import SimpleNamespace
    from nucleo import consent
    from nucleo.workers import exit_gate
    from nucleo.workers.prompts import playbook
    from widgets import contract
    call = {"contact": "Quinn", "text": "the numbers"}
    out = rig.run("mensajeria", "send_to", dict(call), said="send the numbers to the team", monkeypatch=monkeypatch)
    assert not out.ran and not out.asked and any("goes to its owner" in label for _k, label in out.events), out
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)     # the door's question, not a channel probe
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    rec = SimpleNamespace(task_id="t-quinn", playbook_chosen="message", uid="t-quinn", started=time.time(), depth=0,
                          trace_id="", surface="", sheet="", mandate={}, reading=None,
                          heard=["send the numbers to the team"], own_words=True)
    ex = exit_gate.leave(rec, "widget_data", {"widget_id": "mensajeria", "action": "send_to", "payload": call})
    consent._reset_for_tests()
    assert ex is not None and ex.verdict == "ask" and "Quinn" in ex.question, ex

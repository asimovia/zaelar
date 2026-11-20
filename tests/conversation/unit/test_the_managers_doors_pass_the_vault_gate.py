"""His words pass the vault gate at the manager's one door, voice and typed alike, before they reach the store or the
model (node 13.126, V2-941 — a security hole the advisor found: the gate ran only at the old turn's door, so a secret
he said in a session of the manager reached the model).

  · a secret (or a security rule) that IS the line is consumed: nothing enters, its line is owed to him, and the voice's
    discard keeps only the redacted text — never the value;
  · a secret inside a line goes on redacted.

Disarms seen red: the gate removed from the ear's guards; the gate removed from the typed door.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conversation.ear.arbiter import DISCARD, REPLACE
from nucleo.conversation_host import entry, guards
from memory.vault import gate as vault_gate


@pytest.fixture
def gate(monkeypatch):
    owed: list[str] = []
    seen: list[str] = []

    def inspect_now(text, *, enabled=True, store=True):
        seen.append(text)
        if text == "w_secret":
            return vault_gate.VaultVerdict(kind="saved", consumed=True, text="[secret]", line="w_saved")
        if "w_secret" in text:
            return vault_gate.VaultVerdict(kind="carried", text=text.replace("w_secret", "[secret]"))
        return vault_gate.VaultVerdict(text=text)
    monkeypatch.setattr(vault_gate, "inspect_now", inspect_now)
    monkeypatch.setattr(guards, "_owe", owed.append)
    monkeypatch.setattr(guards, "judge", lambda text, now=None, rose=None: None)
    from voice import attention
    monkeypatch.setattr(attention, "has_wakeword", lambda text: False)
    return SimpleNamespace(owed=owed, seen=seen)


def test_his_voice_passes_the_gate_before_it_enters(gate):
    why = guards.for_ear("holder", "w_secret")
    assert why[0] == DISCARD and why[1] == "vault" and "w_secret" not in why[2], why
    assert gate.owed == ["w_saved"]
    assert guards.for_ear("holder", "w1 w_secret w2") == (REPLACE, "w1 [secret] w2")
    assert guards.for_ear("holder", "w1 w2") is None


def test_a_typed_line_passes_the_same_gate(gate, monkeypatch):
    handed = []
    monkeypatch.setattr(entry, "_hand", handed.append)
    heard = []
    conv = SimpleNamespace(hear=heard.append)
    entry.typed("w_secret", "desktop:d1", checked=True)
    entry.typed("w1 w_secret", "desktop:d1", checked=True)
    for deliver in handed:
        deliver(conv)
    assert [s.text for s in heard] == ["w1 [secret]"] and gate.owed == ["w_saved"]

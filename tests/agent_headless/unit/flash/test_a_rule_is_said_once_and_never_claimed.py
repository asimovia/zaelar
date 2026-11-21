"""A rule he states is said once, by the turn, and never claimed when no gate can apply it (V2-852 M3/M4).

Session 94be1e1e: «no me pidas confirmación para mandar mensajes a Raquel» — the turn answered «Got it — no more
confirmations», then the rule writer, off the turn, said «Entendido: no te pido confirmación…» in another language:
two mouths for one fact. And the row was a NOTE at a consent class's scope, which no gate reads, so the next send
asked again — both lines had promised the opposite. Since V2-857 phase 2 a rule about one person IS applicable (a
gate row at `subject:<id>…`, node 2.1612); a note at a class scope that names a person is one the shaper did not
apply, and the line says so — kept, not applied, and how to say it so it applies — never that it cannot.
"""
from __future__ import annotations


import pytest


_NOTE_AT_A_CLASS = {"op": "add", "say": "Entendido: no te pido confirmación para Raquel.",
                    "stored": [{"id": "r1", "scope": "messaging/*/send_new", "kind": "pref", "key": "note",
                                "text": "no me pidas confirmación para mandar mensajes a Raquel"}]}
#: a note at the same class scope whose words name nobody: a preference, not a per-person exception (H10)
_NOTE_NAMING_NOBODY = {"op": "add", "say": "Noted: work messages preferably by email.",
                       "stored": [{"id": "r3", "scope": "messaging/*/send_new", "kind": "pref", "key": "note",
                                   "text": "for work things, better by email"}]}
_A_GATE = {"op": "add", "say": "Got it: WhatsApp goes out without asking.",
           "stored": [{"id": "r2", "scope": "messaging/whatsapp/send_new", "kind": "gate", "key": "consent", "text": "x"}]}


@pytest.mark.parametrize("pack", ["en", "es"])
def test_the_line_exists_in_every_pack(pack):
    from i18n import langs
    assert langs.spec(pack).rule_kept_not_applied


"""The manager's configuration comes from data, and his rule applies with no restart (node 13.38, v3.1 §1.9, B2).

The graces are genome thresholds: genesis `conversation.thresholds`, each inside the bounds `genome.thresholds`
declares for it; a value out of its bounds, a knob nobody declared or a set out of the graces' order is refused. The
hold behind an open voice is the typed lane's own cap. Whether a text he types with his voice live is answered by
voice too is HIS rule (`reply_voice_to_text`, a default row from genesis): a row of his changes the next reply. The
row and the knob exist only for an account with the manager switched on: off, the old path sees nothing new.
"""
from __future__ import annotations

import json

import genome
import rules
from conversation.config import Config
from nucleo.conversation_host import config as host_config
from nucleo.input import typed
from rules.scope import VOICE
from tests.conversation.unit.convkit import Harness


def _genesis() -> dict:
    return json.loads(json.dumps(genome.genesis()))


def test_the_genesis_config_is_the_designed_one_and_passes():
    cfg, problems = host_config.build()
    assert problems == []
    designed = Config()
    for knob in ("complete_grace_ms", "terminal_grace_ms", "nonterminal_start_ms", "nonterminal_grace_ms",
                 "incomplete_grace_ms"):
        assert getattr(cfg, knob) == getattr(designed, knob), knob
    assert cfg.cross_channel_hold_ms == int(typed.CAP_S * 1000)
    assert genome.check(genome.genesis()) == []


def test_every_threshold_of_the_manager_is_a_declared_gene():
    g = genome.genesis()
    declared = set((g["genome"]["thresholds"]))
    assert {host_config.PREFIX + k for k in g["conversation"]["thresholds"] if not k.startswith("_")} <= declared


def test_a_value_out_of_its_bounds_or_undeclared_is_refused():
    g = _genesis()
    g["conversation"]["thresholds"]["incomplete_grace_ms"] = 9000
    g["conversation"]["thresholds"]["patience_ms"] = 100
    _cfg, problems = host_config.build(g)
    assert any(p.startswith("incomplete_grace_ms: 9000") for p in problems)
    assert any(p.startswith("patience_ms:") for p in problems)


def test_a_set_out_of_order_is_refused():
    g = _genesis()
    g["conversation"]["thresholds"]["terminal_grace_ms"] = 5500
    _cfg, problems = host_config.build(g)
    assert problems == ["terminal_grace_ms > nonterminal_grace_ms"]


def test_his_rule_changes_the_reply_channel_with_no_restart(store, monkeypatch):
    h = Harness(store, grace=False, prefs=host_config.prefs)
    h.conv.device("d2", voice_live=True, speaker_open=True)
    h.typed("w1", 100)
    h.at(1000).pump()
    assert "voice" in h.mouth.orders[-1].channels                      # the factory row: a text gets voice too
    row = rules.add(VOICE, "pref", "reply_voice_to_text", False, text="w0")
    try:
        h.typed("w2", 2000)
        h.at(3000).pump()
        assert h.mouth.orders[-1].channels == frozenset({"text"})      # his row, at the next reply
    finally:
        rules.remove(row["id"])
    h.typed("w3", 4000)
    h.at(5000).pump()
    assert "voice" in h.mouth.orders[-1].channels


def test_the_managers_knobs_are_every_accounts_rules(monkeypatch):
    """The manager is the only path (INI-078 F2): its preferences are on every account's rules panel and offered to
    the rule shaper — never a style knob."""
    from rules import defaults, vocabulary
    assert [r["value"] for r in rules.all_rows() if r["key"] == "reply_voice_to_text"] == [True]
    assert "reply_voice_to_text" in vocabulary.knobs()
    assert "reply_voice_to_text" not in defaults.style_keys()                            # never a style knob

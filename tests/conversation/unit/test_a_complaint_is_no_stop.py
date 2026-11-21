"""A complaint about what the agent said, or how, is no stop (node 13.147, C5).

His long complaint («you are repeating yourself like a parrot…») was read as `stop_run` and the answer was dropped:
silence, to a complaint. The stop rule the model reads is declared data: it names a complaint about what was said or
how as NO stop — something to answer — and `stop_run` is cancelling the work in course, nothing else. The prefix carries
the rule as declared.
"""
from __future__ import annotations

from nucleo.conversation_host import prefix
from nucleo.conversation_host.declared import declared


def test_the_declared_stop_rule_names_a_complaint_as_no_stop_and_the_prefix_carries_it():
    rule = declared()["stop_rule"]
    assert "complaint" in rule and rule.endswith("is no stop: answer it")
    assert "work you are doing for him" in declared()["stops"]["stop_run"]
    assert rule in prefix.build([], native="w_lang", name="w_name")

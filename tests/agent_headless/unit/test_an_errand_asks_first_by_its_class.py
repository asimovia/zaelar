"""An errand asks before it starts by its CLASS, through the one act-or-ask rule (refactor2710-06 T-03).

The class is the brief's `errand_class`, carried in the errand's context — and ONLY that (V2-857 phase 4, node
2.1614): the money vocabulary no longer fills it, and only a critical class (money, his accounts) asks at birth. The
decision is `consent.decide_act`: his yes clears it, his standing «never» refuses.
"""
from __future__ import annotations

import pytest

from nucleo.acts import errand

PAY = "paga la factura de la luz de este mes"


def test_the_class_is_the_verdict_and_the_vocabulary_only_fills_it():
    assert errand.class_of(None, PAY) == "none", "the words decided the class (V2-857 phase 4: the brief alone does)"
    assert errand.class_of(None, "busca hoteles en Sevilla") == "none"
    assert errand.class_of({"choice": "sends_for_him", "confidence": 0.6}, "busca hoteles en Sevilla") == "sends_for_him"
    assert errand.class_of({"choice": "none", "confidence": 0.7}, PAY) == "none"
    assert errand.class_of({"choice": "moves_money", "confidence": 0.7}, "busca hoteles") == "moves_money"
    assert errand.class_of({"choice": "moves_money", "confidence": 0.4}, "busca hoteles") == "none", "below the licence"


def test_money_asks_until_his_yes_and_a_look_never_asks():
    assert errand.asks_first("moves_money", confirmed=False)
    assert errand.asks_first("account_change", confirmed=False)
    assert not errand.asks_first("moves_money", confirmed=True)
    assert not errand.asks_first("none", confirmed=False)


def test_his_standing_never_refuses_even_after_a_yes(monkeypatch):
    from nucleo import consent
    monkeypatch.setattr(consent, "class_policy", lambda key, scope=None: "never" if key.startswith("errand.") else "")
    assert errand.asks_first("moves_money", confirmed=True)


@pytest.mark.parametrize("cls", ["moves_money", "account_change"])
def test_the_dispatch_gate_reads_the_same_rule(cls):
    assert errand.asks_first(errand.class_of({"choice": cls, "confidence": 0.95}, "busca hoteles"), confirmed=False)


def test_the_one_door_that_starts_a_worker_hands_the_verdict_over():
    """`dispatch._run_session` is where the birth asks: it must pass the brief's verdict, or every class reads sure."""
    import inspect
    from nucleo.dispatch import session
    assert 'verdict=task.context.get("errand_class")' in inspect.getsource(session)

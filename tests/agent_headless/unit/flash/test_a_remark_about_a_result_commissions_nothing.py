"""A remark about a result is answered with words: it starts no work (V2-931, 2026-11-17).

Measured on his engine, 23:09: «el mensaje lo veo en el widget de mensajería como enviado, eso debería ser
suficientemente fiable, y además debería mostrar realmente el estado…» — the brief read `complaint` and a sure
`handle_inline` (0.96), the model called `escalate_to_slowbrain` with «improve the messaging widget», the commission
gate kept it for lack of evidence, and he was asked whether to rewrite his card. A turn the verdict reads as talk
ABOUT us (a comment, a complaint) with a sure «no worker needed» commissions nothing; an order, or a turn the verdict
would escalate, keeps its commission. The verdict decides — never his words. ES and EN are the same verdicts.
"""
import pytest

from nucleo.flash import escalation_guard as eg


@pytest.fixture
def brief(monkeypatch):
    verdicts = {"request_type": "complaint", "escalate_or_inline": "handle_inline"}
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda handle, key, fallback, **k: (
        (verdicts[key], {"confidence": 0.9}) if key in verdicts else (fallback, None)))
    monkeypatch.setattr(eg, "a_question_the_state_answers", lambda b: False)
    monkeypatch.setattr(eg, "reply_promises", lambda *a, **k: False)
    return verdicts


def _settle():
    req = {"v": "Improve the messaging widget: show the connector's delivery state", "more": ["and a badge"]}
    v = eg.settle_commission(req, brief=object(), operator_text="the widget shows it as sent, that should be enough",
                             reply="You are right.", acted=False, anything_running=False, emit=lambda *a, **k: None)
    return v, req


@pytest.mark.parametrize("kind", ["complaint", "comment"])
def test_talk_about_us_with_a_sure_inline_verdict_annuls_the_models_commission(brief, kind):
    brief["request_type"] = kind
    v, req = _settle()
    assert (v["annul"], v["why"]) == (True, "a-comment-commissions-nothing")
    assert req["v"] is None and req["more"] == [], "no worker, no «shall I rewrite your card?»"


@pytest.mark.parametrize("key, other", [("request_type", "order"), ("request_type", "question"),
                                        ("escalate_or_inline", "escalate")])
def test_an_order_or_a_turn_the_verdict_escalates_keeps_its_commission(brief, key, other):
    brief[key] = other
    v, req = _settle()
    assert v["annul"] is False and req["v"], (key, other, v)


def test_a_send_handed_over_is_never_annulled_by_it(brief):
    """A leaving act the turn handed to its worker is the commission, whatever the turn's kind reads."""
    req = {"v": "tell Quinn good night", "leaves": True, "send": {"widget": "mensajeria", "action": "send_to"}}
    v = eg.settle_commission(req, brief=object(), operator_text="x", reply="", acted=False, anything_running=False,
                             emit=lambda *a, **k: None)
    assert v["annul"] is False and req["v"]


def test_disarmed_the_remark_is_commissioned_again(brief, monkeypatch):
    """Disarm: without the reading of the turn's kind the commission survives as «unresolved» (seen red)."""
    monkeypatch.setattr(eg, "talks_about_us", lambda b: False)
    v, req = _settle()
    assert v["annul"] is False and v["disposition"] == eg.UNRESOLVED and req["v"]

"""The launch's event says what happened: a join is not an escalation (node 2.1669, V2-874 rule 4).

Measured on a demo turn (2026-11-10, es S3 events 1195-1197): `flow_of` injected «abre el que sea mejor oferta» into
the live monitors errand — and the close logged «Flash → Brain Worker (escalada registrada)», the label of a NEW
errand. The panel is where the operator reads what the turn did. Disarm: every launch labelled an escalation → red.
"""
from __future__ import annotations

import pytest

from nucleo.turn import flow_of
from nucleo.turn import pipeline_errands as PE


@pytest.fixture(params=["es", "en"])
def lang(request):
    return request.param


@pytest.mark.parametrize("joins_as", [flow_of.INJECT, "steer", flow_of.ABSORB, flow_of.REOPEN, flow_of.JOIN])
def test_a_join_is_labelled_as_the_join_it_was(lang, joins_as):
    label = PE.launch_label(joins_as)
    assert "escalada" not in label and f"({joins_as})" in label


@pytest.mark.parametrize("joins_as", [flow_of.NEW, ""])
def test_a_new_errand_keeps_its_escalation_label(lang, joins_as):
    assert PE.launch_label(joins_as) == "🧭 Flash → Brain Worker (escalada registrada)"

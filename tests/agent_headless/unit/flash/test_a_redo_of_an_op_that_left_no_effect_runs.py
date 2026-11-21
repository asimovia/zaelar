"""V2-791 · A re-emitted op is a drag only when the previous one LANDED and the turn did not ask for it again.

The measured shape (one session, a video card open): `youtube:channel_videos` ran once and filled the queue
behind the player face, so nothing on screen changed. He complained three times — «¿lo vas a hacer en el widget de
YouTube que estoy viendo?», «no estás haciendo nada con el widget de YouTube», «quiero que lo hagas directamente» —
the model re-emitted the same op each time, and the anti-drag guard ate every one as context-bleed while the
reply promised it.

The guard keeps its job (the original drag: a write repeated by a turn about something else); what it can no longer
do is eat a REDO. Three structural readings license one, none of them a phrase table:

  · the card reported that the previous op did not happen (`widgets/late_report.falsified_since`);
  · his turn names that card as its target (`named_target.names_it`; a card named to be left alone does not count);
  · the redo verdict reads the turn as a correction of the op on that card (when a verdict exists).
"""
from __future__ import annotations

import time

import pytest


from nucleo.acts import data_ops
from widgets import late_report

_PAYLOAD = {"channel": "José Luis Cárpatos"}


def _last(ts=None, wid="youtube", action="channel_videos", payload=None):
    return (wid, action, dict(payload if payload is not None else _PAYLOAD), time.time() - 5 if ts is None else ts)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(late_report, "_falsified", {})
    monkeypatch.setattr(late_report, "_last_agent_order", {})


def _bleed(said, last=None, wid="youtube", action="channel_videos", payload=None, brief=None):
    return data_ops.is_context_bleed(last or _last(), wid, action, dict(payload if payload is not None else _PAYLOAD),
                                     said, brief=brief)


def test_a_late_report_with_no_agent_order_falsifies_nothing():
    """His own click on a dead control is in front of him: nobody promised it, nothing to retry."""
    late_report.deliver("youtube", {"tell": "el navegador no deja activar el sonido"})
    assert not late_report.falsified_since("youtube", 0)

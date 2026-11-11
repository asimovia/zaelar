"""V2-887 step 5 — a clear request is DONE with what there is, and nothing is called done before its result.

Measured 2026-11-11 (local session): «añádeme el viernes de 12 a 8, partido del X» → «¿te confirmo el nombre tal
cual?» and no call (the verdict said `agenda:add_meeting` 0.89, act 0.94); «mándale un mensaje a Raquel» → «Hecho.»
at 4.19 s while the send, routed to its task, failed at 4.37 s (ten Raquels).

  · the turn prompt tells the model to act on a clear request and ask only for a missing fact, never «shall I?»;
  · an act that left as a task (`escalate_req["send_task"]`) is said as a START, never as the short «Hecho.».
"""
from __future__ import annotations

import inspect

from nucleo.flash import post_stream_settle
from nucleo.turn.prompt import operating


def test_the_prompt_says_act_and_ask_only_a_missing_fact():
    src = inspect.getsource(operating)
    assert "Una PETICIÓN clara se HACE ya" in src and "nunca «¿lo hago?»" in src


def test_a_send_that_left_as_a_task_is_a_start_never_the_short_done():
    src = inspect.getsource(post_stream_settle)
    start = src.index('if escalate_req.get("send_task") and data_done["v"] and not spoken_text:')
    assert "routed_send_started" in src[start:start + 300]
    from nucleo.turn import reply
    said = []
    assert reply.routed_send_started(said.append, type("S", (), {"sanitize": staticmethod(lambda t, **k: t)})) \
        and said and "Hecho" not in said[0]
    ack = src.index('if data_done["v"] and not spoken_text and _ack_allowed')
    assert 'not escalate_req.get("send_task")' in src[ack:ack + 200], "the short «Hecho.» still covers a routed send"


def test_the_start_line_exists_in_both_languages():
    import json
    import pathlib
    root = pathlib.Path(operating.__file__).resolve().parents[3] / "i18n" / "genesis"
    for lang in ("es", "en"):
        assert json.loads((root / lang / "voice.json").read_text())["done_just_started"].strip()

"""The commissioning turn's READING rides with its task (V2-852, after the audit of 2026-11-05).

Since an act that leaves is a task (CRIT-T2b), the worker does the send with no turn of its own: what the act needs
from his sentence — the channel he named, his sure order over the row he saw — was read on Flash's brief and lost on
the way, one wire at a time (the channel was the open one: `message_channel.his_channel` read a brief the worker never
had). Now the brief's verdicts are frozen once on the task (`nucleo/turn/brief.carried`), kept on the record
(`rec.reading`) and revived for the same readers Flash uses. ES and EN words alike: the reading is the verdict, never
his words.
"""
from __future__ import annotations

import threading


from nucleo.turn import brief as tb


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


def test_a_reading_is_plain_data_and_revives_for_every_reader():
    from nucleo.turn import verdicts
    carried = tb.carried(_brief(message_channel=("whatsapp", 0.97), request_type=("order", 1.0)))
    import json
    assert json.loads(json.dumps(carried)) == carried                 # it travels on the bus as plain data
    turn = tb.revived(carried)
    assert verdicts.read(turn, "message_channel", None)[0] == "whatsapp"
    assert tb.carried({"event": threading.Event(), "result": {}}) == {}   # a brief still in flight carries nothing
    assert tb.revived({}) is None


def test_the_escalation_carries_the_turns_reading():
    import inspect
    from nucleo.dispatch import session
    from nucleo.turn import pipeline_errands
    assert '"reading": _tb.carried(_brief)' in inspect.getsource(pipeline_errands.launch_the_errands)
    assert 'rec.reading = dict(task.context.get("reading")' in inspect.getsource(session)

"""What a session of the manager spends is counted as ever (node 13.118, V2-941, plan v3.2 C15) — fixed by tests,
since it holds by construction:

  · the model: the manager's model port speaks through the engine's one fast client (`FastClient`), whose stream asks
    the energy lease first and reports every call's usage (`energy.meter.report_llm_usage`) — no second client;
  · the voice: the voice process wires `metrics_collected` for every session it builds, the manager's included (the
    wiring is not conditional), and the body hands those metrics to the one meter (`metrics_tap.on_metrics`) in a
    session of the manager as in any other.

Disarms seen red: a model port that builds its own client; the body dropping a metric in a session of the manager.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace


def test_the_managers_model_speaks_through_the_engines_one_client():
    from nucleo.conversation_host.model import FastModel
    from nucleo.llm.fast_client import FastClient
    client, _spec = FastModel(spec=SimpleNamespace(model="m"))._parts()
    assert type(client) is FastClient
    assert "energy_lease.admit(\"llm\")" in inspect.getsource(FastClient.stream)
    assert "self._stream_inner(" in inspect.getsource(FastClient.stream)
    assert "report_llm_usage(" in inspect.getsource(FastClient._stream_inner)


def test_the_voice_process_wires_its_metrics_for_every_session():
    from voice.engine.pipeline import child_session
    tree = ast.parse(textwrap.dedent(inspect.getsource(child_session._wire)))
    fn = tree.body[0]
    wired = [d for n in fn.body if isinstance(n, ast.FunctionDef) for d in n.decorator_list
             if isinstance(d, ast.Call) and getattr(d.args[0], "value", None) == "metrics_collected"]
    assert wired, "the metrics are wired at the top of `_wire`, under no condition"
    assert "_wire(session, ctx, link, sm, _emit, tts, boot)" in inspect.getsource(child_session)


def test_the_body_meters_a_session_of_the_managers_voice(monkeypatch):
    from nucleo.conversation_host import switch
    from voice import remote_session as rs
    from voice.engine.pipeline import metrics_tap
    got = []
    monkeypatch.setattr(metrics_tap, "on_metrics", lambda m, emit: got.append(m))
    monkeypatch.setitem(rs._M, "session", SimpleNamespace(_conversation_switch=switch.Decision(True, "voice")))
    rs.handle({"k": "metrics", "type": "TTSMetrics", "characters_count": 12, "audio_duration": 1.5})
    assert len(got) == 1

"""V2-887 — the voice job's thread raises itself to USER_INTERACTIVE on macOS, and the entrypoint asks for it first."""
from __future__ import annotations

import sys
import threading
import inspect

import pytest

from voice.engine.pipeline import thread_qos


@pytest.mark.skipif(sys.platform != "darwin", reason="per-thread QoS classes are macOS")
def test_a_thread_that_asks_is_served_as_interactive():
    got = {}

    def run():
        got["before"] = thread_qos.current()
        got["ok"] = thread_qos.interactive()
        got["after"] = thread_qos.current()
    t = threading.Thread(target=run)
    t.start()
    t.join()
    assert got["ok"] is True
    assert got["after"] == thread_qos.QOS_CLASS_USER_INTERACTIVE != got["before"]


def test_the_voice_entrypoint_asks_before_it_connects():
    from voice.engine.pipeline import agent
    assert "thread_qos.interactive()" in inspect.getsource(agent._before_connect)
    src = inspect.getsource(agent.entrypoint)
    assert src.index("_before_connect()") < src.index("ctx.connect()")

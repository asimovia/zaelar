"""V2-891 — a TTS prewarm runs on the session's loop, and an awaitable it returns is run, never dropped.

Every remote TTS plugin's `prewarm()` schedules its connection on the RUNNING event loop (`asyncio.create_task`); one
may return the coroutine instead. The worker's `setup_fnc` has no running loop: calling it there built a coroutine
that was never awaited (the RuntimeWarning in the voice process's log at every boot) and the failover adapter
swallowed the error, so the first audio of every session paid the cold TLS+WS handshake. Now:

  · `start_prewarm` calls nothing without a running loop (no orphan coroutine) and returns False;
  · inside a loop, a sync prewarm that schedules a task and an async prewarm both reach the connection;
  · the failover adapter warms every voice through it, the stand-in too;
  · both session entrypoints (embedded and the voice's own process) start it BEFORE the room connects, and the
    `setup_fnc` no longer calls a plugin's prewarm.
"""
from __future__ import annotations

import ast
import asyncio
import gc
import warnings
from pathlib import Path

from livekit.agents import tts as lk_tts

from voice.engine.speech import tts as T

ENGINE = Path(__file__).resolve().parents[3]


class _SchedulesATask:
    """The Inworld/OpenAI/Cartesia shape: a sync prewarm that `create_task`s its connection."""

    def __init__(self):
        self.connected = False
        self.called = False

    async def _connect(self):
        self.connected = True

    def prewarm(self) -> None:
        self.called = True
        asyncio.create_task(self._connect())


class _ReturnsTheCoroutine:
    """A plugin whose prewarm is itself a coroutine function."""

    def __init__(self):
        self.connected = False

    async def prewarm(self) -> None:
        self.connected = True


class _Voice(lk_tts.TTS):
    def __init__(self):
        super().__init__(capabilities=lk_tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1)
        self.connected = False

    async def _connect(self):
        self.connected = True

    async def prewarm(self):   # the async shape, inside a real FallbackAdapter
        await self._connect()

    def synthesize(self, text, **kw):  # pragma: no cover — never called here
        raise NotImplementedError


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


def test_without_a_running_loop_nothing_is_called_and_no_coroutine_is_orphaned():
    t = _SchedulesATask()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert T.start_prewarm(t) is False
        assert not t.called, "off the loop the plugin's prewarm must not be called: it builds a coroutine and raises"
        gc.collect()
    orphaned = [w for w in caught if "never awaited" in str(w.message)]
    assert not orphaned, f"a prewarm called off-loop built a coroutine nobody runs: {orphaned[0].message}"


def test_a_sync_prewarm_reaches_its_connection_on_the_loop():
    t = _SchedulesATask()

    async def _run():
        assert T.start_prewarm(t) is True
        await _settle()
    asyncio.run(_run())
    assert t.connected


def test_an_async_prewarm_is_run_not_dropped():
    t = _ReturnsTheCoroutine()

    async def _run():
        assert T.start_prewarm(t) is True
        await _settle()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        asyncio.run(_run())
        gc.collect()
    assert t.connected, "the coroutine the prewarm returned was never run"
    assert not [w for w in caught if "never awaited" in str(w.message)]


def test_the_failover_warms_every_voice_the_stand_in_too():
    a, b = _Voice(), _Voice()
    adapter = T._with_failover([("inworld", a), ("elevenlabs", b)])

    async def _run():
        assert T.start_prewarm(adapter) is True
        await _settle()
    asyncio.run(_run())
    assert a.connected and b.connected


def _calls_before_connect(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "entrypoint")
    names = []
    for stmt in fn.body:
        if "ctx.connect" in ast.unparse(stmt):
            return names
        names += [ast.unparse(c.func) for c in ast.walk(stmt) if isinstance(c, ast.Call)]
    raise AssertionError(f"{path.name}: entrypoint never connects the room")


def test_both_entrypoints_warm_the_tts_before_the_room_connects():
    for rel in ("voice/engine/pipeline/agent.py", "voice/engine/pipeline/child_session.py"):
        before = _calls_before_connect(ENGINE / rel)
        assert any(n.endswith("_warm_tts") for n in before), f"{rel}: the TTS is not warmed before connect"
    from voice.engine.pipeline import agent
    got = []
    real = agent.start_prewarm
    try:
        agent.start_prewarm = got.append
        agent._warm_tts(type("Ctx", (), {"proc": type("P", (), {"userdata": {"tts": "warm"}})()})())
        agent._warm_tts(object())                                   # a context without a process warms nothing
    finally:
        agent.start_prewarm = real
    assert got == ["warm", None], got


def test_the_setup_fnc_calls_no_plugin_prewarm():
    src = (ENGINE / "voice/engine/pipeline/prewarm.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "prewarm")
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            reaches = func.endswith("prewarm") or (
                func == "getattr" and any(isinstance(a, ast.Constant) and a.value == "prewarm" for a in node.args))
            assert not reaches, f"setup_fnc has no running loop, yet calls a prewarm: {ast.unparse(node)}"

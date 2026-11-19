"""INI-042 #34 — the voice's LLM vendor SDKs are imported at boot in a thread, not when the first session opens.

Building the session's LLM imports every provider, each pulls a LiveKit plugin, and the plugins import large vendor
SDKs (`anthropic`, `openai`, `google.genai`): 4.6 s on the body's loop thread at session open, hosted account. The
plugins must stay on the main thread (LiveKit refuses to register one elsewhere), so the boot warms THEIR vendor
modules in a daemon thread, derived from the sources — never a hand list.
"""
from __future__ import annotations

import sys
import threading

from server.boot import surfaces, warm_imports


def test_the_list_is_derived_and_holds_the_heavy_sdks_and_no_plugin():
    plugins = warm_imports.plugins_used()
    assert "livekit.plugins.anthropic" in plugins
    mods = warm_imports.vendor_modules()
    assert {"anthropic", "openai"} <= set(mods)
    assert any(m.startswith("google.genai") for m in mods)
    assert not [m for m in mods if m.split(".")[0] in ("livekit", "voice")]


def test_the_warm_runs_in_a_daemon_thread_and_imports_without_registering_a_plugin(monkeypatch):
    seen = []
    monkeypatch.setattr(warm_imports, "vendor_modules", lambda: ["json", "no_such_module_ini042"])
    real = warm_imports.importlib.import_module
    monkeypatch.setattr(warm_imports.importlib, "import_module",
                        lambda name: (seen.append(threading.current_thread() is threading.main_thread()), real(name))[1])
    t = warm_imports.start()
    assert t.daemon
    t.join(10)
    assert seen == [False, False]


def test_the_boot_starts_the_warm_with_the_voice(monkeypatch):
    started = []
    monkeypatch.setattr(warm_imports, "start", lambda: started.append(1))
    monkeypatch.setenv("ZAELAR_ENGINE", "livekit")
    import voice.child_process as cp
    monkeypatch.setattr(cp, "factory", lambda: (_ for _ in ()).throw(RuntimeError("no voice in a unit test")))

    class _App:
        class state:
            pass
    surfaces.voice_worker(_App())
    assert started == [1]

"""One engine per machine (2026-10-21).

A restart left the old engine alive without its port, beside the new one: two voice workers, two sets of connector
pollers, and a person speaking to a room nobody answered. The engine now holds an OS lock for its whole life; a
second boot refuses, `start` names the survivor, and `stop` ends it even when it holds no port at all.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

_HOLDER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from nucleo import one_engine
assert one_engine.hold(sys.argv[2]) is None
print("held", flush=True)
while True: time.sleep(1)
"""


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ENGINE / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _holder(tmp_path, root):
    env = dict(os.environ, ZAELAR_LOCK_DIR=str(tmp_path))
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(ENGINE), root], stdout=subprocess.PIPE,
                            text=True, env=env)
    assert proc.stdout.readline().strip() == "held"
    threading.Thread(target=proc.wait, daemon=True).start()   # the test is its parent: reap it like init would
    return proc


def test_a_second_engine_is_refused_and_a_dead_one_frees_the_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_LOCK_DIR", str(tmp_path))
    one = _load("one_engine_t", "nucleo/one_engine.py")
    assert one.holder() is None
    proc = _holder(tmp_path, "/some/checkout")
    try:
        seen = one.holder()
        assert seen and seen["pid"] == proc.pid and seen["root"] == "/some/checkout"
        assert one.hold(str(ENGINE)) == seen, "a second engine took the lock beside a live one"
        proc.kill()   # no shutdown, no cleanup: the kernel alone releases the lock
        proc.wait(timeout=5)
        assert one.holder() is None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_ends_an_engine_that_holds_no_port(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_LOCK_DIR", str(tmp_path))
    z = _load("zaelar_launcher_one", "scripts/zaelar.py")
    monkeypatch.setattr(z, "PORTS", [])
    monkeypatch.setattr(z, "_unload_ollama", lambda: None)
    monkeypatch.setattr(z, "live_work", lambda: [])
    monkeypatch.setattr(z, "load_pids", lambda: {})
    monkeypatch.setattr(z, "save_pids", lambda d: None)
    proc = _holder(tmp_path, z.ROOT)
    try:
        assert z.cmd_stop(grace=1.0) == 0
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_start_refuses_while_an_engine_is_alive(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ZAELAR_LOCK_DIR", str(tmp_path))
    z = _load("zaelar_launcher_one_s", "scripts/zaelar.py")
    monkeypatch.setattr(z, "port_busy", lambda *a, **k: False)
    proc = _holder(tmp_path, "/another/copy")
    try:
        assert z.cmd_start() == 1
        assert str(proc.pid) in capsys.readouterr().out
    finally:
        proc.kill()

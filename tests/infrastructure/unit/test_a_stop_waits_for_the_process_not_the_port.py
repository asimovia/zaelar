"""A stop ends the PROCESS, not just its port (2026-10-21).

On SIGTERM the server closed its listener at once and then hung in its own shutdown. `stop` watched the port, saw it
free, reported «stopped» and never escalated; the restart started a second engine while the first one lived on —
still in the voice room, still polling the connectors. The person spoke, the text reached the chat, nobody answered.
"""
from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import threading
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

# Listens, and on SIGTERM closes the listener and hangs: the exact shape of the wedged shutdown.
_WEDGED = r"""
import signal, socket, sys, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 0)); s.listen(); print(s.getsockname()[1], flush=True)
def term(*_):
    s.close()
    while True: time.sleep(1)
signal.signal(signal.SIGTERM, term)
while True: time.sleep(1)
"""


def _reaped(proc):
    """The real engine is not the launcher's child, so init reaps it; here the test is the parent and must reap, or
    the ended process lingers as a zombie that `pid_alive` rightly still sees."""
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def _launcher():
    spec = importlib.util.spec_from_file_location("zaelar_launcher_stop", ENGINE / "scripts" / "zaelar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_process_that_frees_its_port_and_hangs_is_killed(monkeypatch):
    z = _launcher()
    proc = subprocess.Popen([sys.executable, "-c", _WEDGED], stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline())
        _reaped(proc)
        monkeypatch.setattr(z, "pids_on_port", lambda p: [proc.pid] if p == port else [])
        assert z._stop_port(port, "wedged", grace=1.0)
        proc.wait(timeout=5)
        assert proc.returncode is not None, "the process outlived a stop that called itself done"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_a_process_that_ends_politely_is_not_forced(monkeypatch, capsys):
    z = _launcher()
    proc = subprocess.Popen([sys.executable, "-c",
                             "import socket,time;s=socket.socket();s.bind(('127.0.0.1',0));s.listen();"
                             "print(s.getsockname()[1],flush=True);time.sleep(60)"],
                            stdout=subprocess.PIPE, text=True)
    try:
        port = int(proc.stdout.readline())
        _reaped(proc)
        monkeypatch.setattr(z, "pids_on_port", lambda p: [proc.pid] if p == port else [])
        assert z._stop_port(port, "polite", grace=3.0)
        proc.wait(timeout=5)
        assert "forced" not in capsys.readouterr().out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

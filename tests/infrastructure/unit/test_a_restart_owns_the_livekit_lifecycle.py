"""A restart must own LiveKit's lifecycle (reset left voice dead, 2026-11-11).

The old livekit-server drains gracefully on SIGTERM and keeps its ports meanwhile; the new one then dies on
"address already in use" and the probe answers from the dying old one. `lk_reap_old` must not return until the
old process is really gone (SIGKILL past a deadline), and the launcher must supervise the server it started.
"""
import os
import subprocess
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
LIB = ENGINE / "scripts" / "lib" / "livekit-ownership.sh"
LAUNCHER = ENGINE / "scripts" / "run-livekit.sh"
TAG = "livekit-server --dev --zaelar-test-%d" % os.getpid()


def _spawn_stubborn():
    """A stand-in that IGNORES SIGTERM, like a LiveKit draining its participants."""
    return subprocess.Popen(["bash", "-c", 'trap "" TERM; while :; do sleep 0.2; done', *TAG.split()])


def _reap(term_wait, kill_wait):
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; lk_reap_old "{TAG}" {term_wait} {kill_wait}'], timeout=30
    ).returncode


def test_reap_waits_until_a_term_ignoring_server_is_gone():
    p = _spawn_stubborn()
    try:
        time.sleep(0.5)
        t0 = time.time()
        assert _reap(1, 4) == 0
        assert time.time() - t0 >= 1, "returned before the SIGTERM grace elapsed"
        assert p.wait(timeout=5) is not None  # really dead, not merely signalled
    finally:
        p.kill()


def test_reap_with_nothing_running_is_instant_success():
    assert _reap(1, 1) == 0


def test_launcher_uses_the_helper_and_supervises_its_livekit():
    src = LAUNCHER.read_text(encoding="utf-8")
    assert "lib/livekit-ownership.sh" in src
    assert 'lk_reap_old "livekit-server --dev"' in src
    assert 'pkill -f "livekit-server --dev"' not in src, "fire-and-forget kill is the bug"
    assert "lk_alive" in src and "start_livekit" in src.split("lk_alive", 1)[1], "no relaunch of a dead LiveKit"

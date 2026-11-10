"""The signing calls that cross Apple's network are tried again; a verdict is not (V2-869 §5, node 7.128).

`stapler staple` / `stapler validate` reach Apple's CloudKit service, and a dropped connection there (exit 68,
NSURLErrorDomain -1005) failed a release whose notarization had already been ACCEPTED. What is pinned:

  · `retry` (daemon/packaging/macos/retry.sh) runs the command again after each pause in RETRY_DELAYS, logs every
    attempt, stops at the first success and returns the command's own exit code after the last failure;
  · the default pauses are 15 30 60 90 120 s, and every stapler call of the plan goes through `retry`;
  · `transient` reads a network failure as transient and a notarization verdict as NOT transient, so
    `notarytool submit` is resubmitted only for the first.

Disarm (seen red 2026-11-10): `retry` reduced to a single `"$@"` → the flaky-command test fails (one attempt, exit 68).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.infrastructure.unit.daemon.test_the_macos_signing_plan_runs_inside_out import SECRETS, INSTALLER, _plan

ENGINE = Path(__file__).resolve().parents[4]
RETRY = ENGINE / "daemon" / "packaging" / "macos" / "retry.sh"


def _bash(script: str, tmp_path: Path, delays: str = "0 0 0 0 0") -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin", "ZAELAR_RETRY_DELAYS": delays, "COUNT": str(tmp_path / "count")}
    return subprocess.run(["bash", "-c", f'set -euo pipefail; . "{RETRY}"; {script}'], env=env,
                          capture_output=True, text=True, timeout=30)


# A command that fails with exit 68 (stapler's network failure) until its Nth call.
_FLAKY = 'flaky() { n=$(( $(cat "$COUNT" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$COUNT"; (( n >= $1 )) || return 68; }'


def test_a_flaky_command_is_retried_until_it_succeeds(tmp_path):
    out = _bash(f'{_FLAKY}; retry "stapler staple Zaelar.app" flaky 3; echo done', tmp_path)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("done")
    assert [l for l in out.stdout.splitlines() if "attempt" in l] == [
        f"  ↻ stapler staple Zaelar.app: attempt {i}/6" for i in (1, 2, 3)]
    assert out.stderr.count("exit 68, retrying") == 2
    assert (tmp_path / "count").read_text().strip() == "3"


def test_a_command_that_never_succeeds_fails_with_its_own_exit_after_the_last_attempt(tmp_path):
    out = _bash(f'{_FLAKY}; retry "stapler validate Zaelar.pkg" flaky 99', tmp_path)
    assert out.returncode == 68
    assert out.stdout.count("attempt") == 6
    assert "failed 6 times (last exit 68)" in out.stderr
    assert (tmp_path / "count").read_text().strip() == "6"


def test_success_on_the_first_attempt_waits_for_nothing(tmp_path):
    out = _bash('retry "x" true', tmp_path, delays="15 30 60 90 120")    # a real pause would hit the timeout
    assert out.returncode == 0 and out.stdout.count("attempt") == 1


def test_the_default_pauses_are_15_30_60_90_120(tmp_path):
    out = subprocess.run(["bash", "-c", f'. "{RETRY}"; echo "${{RETRY_DELAYS[*]}}"'], env={"PATH": "/usr/bin:/bin"},
                         capture_output=True, text=True, timeout=10)
    assert out.stdout.strip() == "15 30 60 90 120"


@pytest.mark.parametrize("stderr, expected", [
    ('Error: Error Domain=NSURLErrorDomain Code=-1005 "The network connection was lost."', True),
    ("Error: The request timed out.", True),
    ("Error: HTTP status code: 503. Service Unavailable", True),
    ("Error: Could not connect to the server.", True),
    ('{"status": "Invalid", "message": "Processing complete"}', False),
    ("Error: HTTP status code: 401. Unable to authenticate.", False),
    ("", False),
])
def test_only_a_network_failure_is_transient(tmp_path, stderr, expected):
    err = tmp_path / "notary.err"
    err.write_text(stderr)
    out = _bash(f'transient "{err}"', tmp_path)
    assert (out.returncode == 0) is expected, (stderr, out.returncode)


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("plutil"),
                    reason="the signing script reads Info.plist with macOS plutil")
def test_every_stapler_call_and_the_notary_submit_carry_the_retry_in_the_plan(tmp_path):
    lines, _ = _plan(tmp_path, {**SECRETS, **INSTALLER})
    stapler = [i for i, l in enumerate(lines) if l.startswith("+ xcrun stapler ")]
    assert len(stapler) == 4, lines
    for i in stapler:
        assert lines[i + 1].startswith("  ↻ ") and "up to 6 attempts, pauses 15 30 60 90 120 s" in lines[i + 1], \
            (lines[i], lines[i + 1])
    submits = [i for i, l in enumerate(lines) if l.startswith("+ xcrun notarytool submit")]
    assert len(submits) == 2
    for i in submits:
        assert "on a network error only" in lines[i + 1], lines[i + 1]

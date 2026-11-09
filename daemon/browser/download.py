"""Fetching a Chromium on a computer with no Google Chrome: one background job, with progress, that can be cancelled.

WHAT RUNS. `playwright install --no-shell chromium`, through the Node driver the daemon ships with (the bundled
`playwright` package's `driver/node` + `driver/package/cli.js`). `--no-shell` because the daemon only ever opens
HEADED windows: the headless shell would be another ~100 MB nobody uses. The browser lands in Playwright's own cache
(see `channel.cache_dirs`), which is where `channel.chromium_dir` looks for it afterwards.

THE STATE MACHINE, which is what `/health` and the tray show:

    idle ──start()──▶ downloading ──exit 0 + marker──▶ ready
                          │  ├──cancel()───────────────▶ cancelled
                          │  └──exit ≠ 0 / no marker────▶ failed
    cancelled / failed ──start()──▶ downloading

PROGRESS IS READ, NOT INVENTED. Playwright prints `|■■■■   |  40% of 171 MiB` lines while it downloads; the job parses
the percentage and the size of the CHROMIUM download (it may fetch a small helper after it, whose own 0→100 % must not
make the bar jump backwards). With no such line yet the job says 0 % and 0 MB, never a guess.

A CANCEL IS FINAL FOR THIS PROCESS AND REMEMBERED. The process is terminated (killed if it does not stop), and
`browser.auto_download` is set to false so the next start of the daemon does not begin the same download the person
just stopped. The half-written folder is left for Playwright, which resumes or replaces it on the next install; it is
never mistaken for a browser because it has no `INSTALLATION_COMPLETE` marker.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time

from .. import config
from . import channel

_PROGRESS = re.compile(r"(\d{1,3})%\s+of\s+([\d.]+)\s*(KiB|MiB|GiB|KB|MB|GB)")
_UNIT_MB = {"KiB": 1 / 1024, "KB": 1 / 1000, "MiB": 1.0, "MB": 1.0, "GiB": 1024.0, "GB": 1000.0}
_STOP_GRACE_S = 5.0


def parse_progress(line: str) -> tuple[int, float] | None:
    """`(percent, size_mb)` from one line of Playwright's output, or None for any other line."""
    m = _PROGRESS.search(line or "")
    if not m:
        return None
    pct = max(0, min(100, int(m.group(1))))
    return pct, round(float(m.group(2)) * _UNIT_MB[m.group(3)], 1)


def install_command() -> list[str]:
    """The Playwright CLI as the bundled driver runs it — no `python -m playwright`, because a frozen daemon has no
    interpreter to give `-m` to."""
    from playwright._impl._driver import compute_driver_executable   # noqa: PLC0415 — optional dependency
    node, cli = compute_driver_executable()
    return [node, cli, "install", "--no-shell", "chromium"]


def _driver_env() -> dict | None:
    try:
        from playwright._impl._driver import get_driver_env   # noqa: PLC0415
        return get_driver_env()
    except Exception:   # noqa: BLE001 — the plain environment still runs the CLI
        return None


class Download:
    """The one download. `command()` and `popen` are injectable so the state machine is testable with a fake."""

    def __init__(self, command=None, popen=subprocess.Popen, installed=None):
        self._command = command or install_command
        self._popen = popen
        self._installed = installed or (lambda: bool(channel.chromium_dir()))
        self._lock = threading.Lock()
        self._proc = None
        self._thread: threading.Thread | None = None
        self._state = "idle"
        self._progress = 0
        self._size_mb = 0.0
        self._error = ""
        self._cancelled = False

    # ── what the outside reads ─────────────────────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            out = {"state": self._state, "progress": self._progress, "size_mb": self._size_mb}
            if self._error:
                out["error"] = self._error
            return out

    @property
    def running(self) -> bool:
        with self._lock:
            return self._state == "downloading"

    # ── the two verbs ──────────────────────────────────────────────────────────────────────────────────────

    def start(self) -> dict:
        """Begin the download unless one is running. Idempotent: a second start is the first one's snapshot."""
        with self._lock:
            if self._state == "downloading":
                return self.snapshot_unlocked()
            try:
                argv = self._command()
                proc = self._popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1, env=_driver_env())
            except Exception as e:   # noqa: BLE001 — no driver, no node: a failed job with a reason, not a crash
                self._state, self._error = "failed", f"could not start the download: {type(e).__name__}"
                return self.snapshot_unlocked()
            self._proc, self._cancelled = proc, False
            self._state, self._progress, self._size_mb, self._error = "downloading", 0, 0.0, ""
            self._thread = threading.Thread(target=self._pump, args=(proc,), name="daemon-browser-download",
                                            daemon=True)
            self._thread.start()
            return self.snapshot_unlocked()

    def cancel(self) -> dict:
        """Stop a running download and remember that the person said no (`browser.auto_download = false`)."""
        with self._lock:
            proc = self._proc if self._state == "downloading" else None
            self._cancelled = True
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=_STOP_GRACE_S)
            except Exception:   # noqa: BLE001 — it did not stop politely
                try:
                    proc.kill()
                except Exception:   # noqa: BLE001
                    pass
        try:
            config.save_browser(auto_download=False)
        except Exception:   # noqa: BLE001 — remembering is best-effort; the cancel itself already happened
            pass
        if self._thread is not None:
            self._thread.join(timeout=_STOP_GRACE_S)
        with self._lock:
            if self._state == "downloading":
                self._state = "cancelled"
            return self.snapshot_unlocked()

    def wait(self, timeout: float | None = None) -> dict:
        """For tests and the CLI: block until the job leaves `downloading`."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.running and (deadline is None or time.monotonic() < deadline):
            time.sleep(0.02)
        return self.snapshot()

    # ── the reader thread ─────────────────────────────────────────────────────────────────────────────────

    def snapshot_unlocked(self) -> dict:
        out = {"state": self._state, "progress": self._progress, "size_mb": self._size_mb}
        if self._error:
            out["error"] = self._error
        return out

    def _pump(self, proc) -> None:
        tracking = None   # True while the lines belong to the Chromium download, False while another one runs
        try:
            for raw in iter(proc.stdout.readline, ""):
                line = raw.strip()
                if line.startswith("Downloading "):
                    tracking = "chrom" in line.lower()
                    continue
                parsed = parse_progress(line)
                if parsed and tracking is not False:
                    with self._lock:
                        self._progress = max(self._progress, parsed[0])
                        self._size_mb = parsed[1]
        except Exception:   # noqa: BLE001 — a closed pipe ends the reading, the exit code decides the outcome
            pass
        code = proc.wait()
        with self._lock:
            if self._cancelled:
                self._state = "cancelled"
            elif code == 0 and self._installed():
                self._state, self._progress = "ready", 100
                try:
                    config.save_browser(channel="chromium")
                except Exception:   # noqa: BLE001
                    pass
            else:
                self._state = "failed"
                self._error = f"the browser download stopped (exit {code})" if code else \
                    "the download finished but no complete browser is on disk"
            self._proc = None


DOWNLOAD = Download()

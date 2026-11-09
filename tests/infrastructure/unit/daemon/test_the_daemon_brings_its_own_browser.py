"""The installed daemon can always open its browser window (V2-575 follow-up · V2-869 §1).

The browser is measured on the computer, never assumed: the person's Google Chrome when it is installed (found where
each OS puts it), otherwise a Chromium the daemon downloads on first run as a background job with progress and a
cancel. `browser.auth` is declared only when a window can really open, the measured channel is recorded in
`daemon.json`, and the transport to the browser is Playwright's pipe — never a debug PORT any local process could join.

Everything runs against fakes: the OS probes are injected, the download is a fake `playwright install` printing the
real output format (measured from Playwright 1.61), and no browser is launched.
Disarms (each seen red): Chrome detection reading only the registry → the `Program Files` case red; the progress
parser dropping the size → red; cancel not remembering `auto_download=false` → red; `available()` ignoring the
measured channel → red; `--remote-debugging-port` added to `LAUNCH_ARGS` → red.
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A daemon with its own throwaway state directory and a fresh config cache."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_DAEMON_BROWSER", raising=False)
    from daemon import config
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


# ── which browser: Google Chrome per OS ───────────────────────────────────────────────────────────────────────

def test_chrome_on_macos_is_found_in_applications_or_the_users_own(tmp_path):
    from daemon.browser import channel
    system = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    users = str(tmp_path / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome")
    assert channel.chrome_executable("darwin", exists=lambda p: p == system, home=tmp_path) == system
    assert channel.chrome_executable("darwin", exists=lambda p: p == users, home=tmp_path) == users
    assert channel.chrome_executable("darwin", exists=lambda p: False, home=tmp_path) == ""


def test_chrome_on_windows_is_found_by_the_registry_then_the_install_folders():
    from daemon.browser import channel
    env = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
           "LOCALAPPDATA": r"C:\Users\p\AppData\Local"}
    custom = r"D:\Apps\Chrome\chrome.exe"
    assert channel.chrome_executable("win32", exists=lambda p: p == custom, registry=lambda: custom, env=env) == custom
    program_files = r"C:\Program Files" + "\\" + r"Google\Chrome\Application\chrome.exe"
    found = channel.chrome_executable("win32", exists=lambda p: p.replace("/", "\\") == program_files,
                                      registry=lambda: "", env=env)
    assert found.replace("/", "\\") == program_files, "a Chrome the registry does not name is still found"
    assert channel.chrome_executable("win32", exists=lambda p: False, registry=lambda: "", env=env) == ""


def test_chrome_on_linux_is_google_chrome_on_path():
    from daemon.browser import channel
    paths = {"google-chrome-stable": "/usr/bin/google-chrome-stable"}
    assert channel.chrome_executable("linux", which=paths.get) == "/usr/bin/google-chrome-stable"
    assert channel.chrome_executable("linux", which=lambda n: None) == ""


def test_only_google_chrome_is_supported_and_health_says_which_are_not():
    """v1 supports Google Chrome as the installed browser; Edge and Firefox are never looked for, and `/health`
    names them so the interface can say it instead of leaving someone wondering why a download starts."""
    from daemon.browser import channel, status
    assert status.health_fields()["unsupported_browsers"] == ["edge", "firefox", "safari"]
    source = (ENGINE / "daemon" / "browser" / "channel.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    for other in ("msedge", "Microsoft\\\\Edge", "firefox.exe", "Firefox.app"):
        assert other not in code, f"the daemon looks for {other}, which v1 does not support"
    assert channel.UNSUPPORTED_BROWSERS == ["edge", "firefox", "safari"]


# ── the downloaded Chromium counts only when it is complete ───────────────────────────────────────────────────

def test_a_half_downloaded_chromium_is_not_a_browser(tmp_path, monkeypatch):
    from daemon.browser import channel
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr(channel, "chromium_revision", lambda: "1228")
    (tmp_path / "chromium-1228").mkdir()
    assert channel.chromium_dir() == "", "a cancelled download leaves the folder without its marker"
    (tmp_path / "chromium-1228" / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")
    assert channel.chromium_dir().endswith("chromium-1228")
    monkeypatch.setattr(channel, "chromium_revision", lambda: "1300")
    assert channel.chromium_dir() == "", "another Playwright's Chromium does not launch under this one"


def test_an_installed_chrome_wins_over_the_downloaded_chromium():
    from daemon.browser import channel
    assert channel.select(chrome=lambda: "/c", chromium=lambda: "/d") == "chrome"
    assert channel.select(chrome=lambda: "", chromium=lambda: "/d") == "chromium"
    assert channel.select(chrome=lambda: "", chromium=lambda: "") == ""


# ── /health and the measured rule ─────────────────────────────────────────────────────────────────────────────

class _Job:
    def __init__(self, snap):
        self._snap = snap

    def snapshot(self):
        return dict(self._snap)


IDLE = _Job({"state": "idle", "progress": 0, "size_mb": 0.0})


@pytest.mark.parametrize("playwright,chosen,job,expected", [
    (False, "chrome", IDLE, {"state": "unsupported", "channel": ""}),
    (True, "chrome", IDLE, {"state": "ready", "channel": "chrome", "progress": 100}),
    (True, "chromium", IDLE, {"state": "ready", "channel": "chromium"}),
    (True, "", IDLE, {"state": "absent", "channel": ""}),
    (True, "", _Job({"state": "downloading", "progress": 40, "size_mb": 171.0}),
     {"state": "downloading", "channel": "chromium", "progress": 40, "size_mb": 171.0}),
])
def test_health_reports_the_browser_state(ws, playwright, chosen, job, expected):
    from daemon.browser import status
    out = status.describe(playwright=lambda: playwright, select=lambda: chosen, job=job)
    for key, value in expected.items():
        assert out[key] == value, (key, out)
    assert set(out) >= {"state", "channel", "progress", "size_mb"}


def test_the_measured_channel_is_recorded_in_daemon_json(ws):
    from daemon import config
    from daemon.browser import status
    assert config.browser() == {"channel": "", "auto_download": True}
    status.describe(playwright=lambda: True, select=lambda: "chrome", job=IDLE)
    on_disk = json.loads((ws / "config" / "daemon" / "daemon.json").read_text(encoding="utf-8"))
    assert on_disk["browser"]["channel"] == "chrome"
    config.reset_cache()
    assert config.browser()["channel"] == "chrome", "the record survives a restart"


def test_a_hand_edited_browser_section_cannot_smuggle_anything_in(ws):
    from daemon import config
    (ws / "config" / "daemon").mkdir(parents=True, exist_ok=True)
    (ws / "config" / "daemon" / "daemon.json").write_text(json.dumps(
        {"browser": {"channel": "/bin/sh", "auto_download": "yes", "profile": "/etc"}}), encoding="utf-8")
    config.reset_cache()
    assert config.browser() == {"channel": "", "auto_download": True}


def test_browser_auth_is_declared_only_when_a_window_can_open(ws, monkeypatch):
    from daemon.browser import channel, window
    from daemon.http import routes
    if not channel.playwright_present():
        pytest.skip("this interpreter has no Playwright: the capability is never declared here")
    monkeypatch.setattr(window, "_chrome_executable", lambda: "")
    monkeypatch.setattr(window, "_chromium_on_disk", lambda: False)
    assert "browser.auth" not in routes.capabilities(), "no browser on disk → no window promised"
    monkeypatch.setattr(window, "_chrome_executable", lambda: "/Applications/Google Chrome.app/c")
    assert "browser.auth" in routes.capabilities(), "an installed Google Chrome is a window the daemon can open"
    monkeypatch.setenv("ZAELAR_DAEMON_BROWSER", "0")
    assert "browser.auth" not in routes.capabilities(), "the person's off switch wins"


def test_health_over_http_carries_the_browser_and_the_unsupported_list(ws):
    """The real route, over a real server: what the interface and the tray read."""
    import threading
    import urllib.request
    from daemon import server as dsrv
    srv = dsrv.build(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/health", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    finally:
        srv.shutdown()
        srv.server_close()
    assert body["unsupported_browsers"] == ["edge", "firefox", "safari"]
    assert body["browser"]["state"] in ("ready", "downloading", "absent", "unsupported")
    assert ("browser.auth" in body["capabilities"]) == (body["browser"]["state"] == "ready"), body
    assert not any(k in json.dumps(body["browser"]) for k in ("/", "\\", "profile")), \
        "the one route without a token names no path"


# ── the first-run download: a job with progress and a cancel ──────────────────────────────────────────────────

# The real output format, measured from `playwright install --no-shell chromium` (1.61) on a pipe.
_FAKE_INSTALL = textwrap.dedent('''
    import sys, time, os, pathlib
    mode = sys.argv[1]
    print("Downloading Chrome for Testing 149.0.7827.55 (playwright chromium v1228) from https://cdn.example/x.zip",
          flush=True)
    for pct in (0, 10, 40):
        print(f"|\\u25a0\\u25a0\\u25a0     |  {pct}% of 171 MiB", flush=True)
        time.sleep(0.02)
    if mode == "hang":
        time.sleep(60)
    for pct in (70, 100):
        print(f"|\\u25a0\\u25a0\\u25a0\\u25a0\\u25a0 | {pct}% of 171 MiB", flush=True)
    print("Downloading FFmpeg (playwright ffmpeg v1011) from https://cdn.example/f.zip", flush=True)
    print("|  | 0% of 1.3 MiB", flush=True)
    print("|\\u25a0| 100% of 1.3 MiB", flush=True)
    if mode == "ok":
        marker = pathlib.Path(sys.argv[2]) / "chromium-1228"
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "INSTALLATION_COMPLETE").write_text("")
    sys.exit(0 if mode != "fail" else 3)
''')


@pytest.fixture
def fake_install(ws, tmp_path, monkeypatch):
    script = tmp_path / "fake_playwright_install.py"
    script.write_text(_FAKE_INSTALL, encoding="utf-8")
    cache = tmp_path / "cache"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    from daemon.browser import channel, download
    monkeypatch.setattr(channel, "chromium_revision", lambda: "1228")

    def make(mode):
        return download.Download(command=lambda: [sys.executable, str(script), mode, str(cache)])
    return make


def test_the_progress_line_is_read_not_invented():
    from daemon.browser.download import parse_progress
    assert parse_progress("|■■■■      |  40% of 171 MiB") == (40, 171.0)
    assert parse_progress("| 100% of 1.3 GiB") == (100, 1331.2)
    assert parse_progress("Downloading Chrome for Testing …") is None


def test_the_download_goes_from_start_to_ready(fake_install, ws):
    from daemon import config
    job = fake_install("ok")
    assert job.snapshot()["state"] == "idle"
    first = job.start()
    assert first["state"] == "downloading"
    assert job.start()["state"] == "downloading", "a second start is the same job, not a second download"
    done = job.wait(timeout=20)
    assert done["state"] == "ready" and done["progress"] == 100, done
    assert done["size_mb"] == 171.0, "the size is Chromium's, not the small helper downloaded after it"
    assert config.browser()["channel"] == "chromium", "the downloaded channel is recorded"


def test_a_cancelled_download_stops_and_is_remembered(fake_install, ws):
    from daemon import config
    job = fake_install("hang")
    job.start()
    from tests.waiting import until_sync
    until_sync(lambda: job.snapshot()["progress"] >= 40, "the download to reach 40 %", timeout_s=4)
    assert job.snapshot()["progress"] == 40, job.snapshot()
    out = job.cancel()
    assert out["state"] == "cancelled", out
    assert config.browser()["auto_download"] is False, "the person said no; the next start must not ask again"


def test_a_download_that_fails_says_so(fake_install):
    job = fake_install("fail")
    job.start()
    out = job.wait(timeout=20)
    assert out["state"] == "failed" and "exit 3" in out.get("error", ""), out


def test_a_download_that_exits_clean_without_a_browser_is_a_failure(fake_install):
    out = fake_install("nomarker")
    out.start()
    snap = out.wait(timeout=20)
    assert snap["state"] == "failed", "exit 0 with no complete browser on disk is not ready"


def test_the_download_runs_the_bundled_driver_without_the_headless_shell():
    from daemon.browser import download
    if not __import__("daemon.browser.channel", fromlist=["x"]).playwright_present():
        pytest.skip("no Playwright here")
    argv = download.install_command()
    assert argv[-3:] == ["install", "--no-shell", "chromium"], argv
    assert argv[0].endswith(("node", "node.exe")) and argv[1].endswith("cli.js"), \
        "a frozen daemon has no interpreter for `python -m playwright`: the bundled Node driver runs it"


# ── the transport: a pipe, never a port ───────────────────────────────────────────────────────────────────────

def test_no_launch_ever_opens_a_debug_port():
    """⚠️ A `--remote-debugging-port` lets ANY local process — a web page's `fetch` included — drive a browser the
    person is signed in to. The sign-in window is driven over Playwright's pipe; the app window has no automation."""
    from daemon.browser import app_window, window
    for chosen in ("chrome", "chromium", ""):
        kwargs = window.launch_kwargs(chosen)
        assert not any("remote-debugging-port" in a for a in kwargs["args"]), kwargs
        assert "cdp" not in json.dumps(kwargs).lower()
    assert window.launch_kwargs("chrome")["channel"] == "chrome"
    assert "channel" not in window.launch_kwargs("chromium")
    argv = app_window.command("/x/chrome", "http://localhost:43917", Path("/p"))
    assert not any("remote-debugging" in a for a in argv), argv
    for path in (ENGINE / "daemon").rglob("*.py"):
        code = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                         if not line.strip().startswith("#"))
        code = re.sub(r'"""[\s\S]*?"""', "", code)
        assert "connect_over_cdp" not in code, f"{path.name} attaches to a browser over CDP"
        assert not re.search(r"""["']--remote-debugging-port""", code), f"{path.name} opens a debug port"

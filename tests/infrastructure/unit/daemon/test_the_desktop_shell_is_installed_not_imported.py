"""The daemon as a desktop resident: a tray icon, the agent in an app window, a `Zaelar.app` — and none of it on the
headless path (V2-575 follow-up · V2-869 §2-§4).

What can break silently, and what each test pins:
  · the tray's GUI library leaks into `python -m daemon` → the headless service needs a desktop to import, and the
    service tests start failing on a server (or, worse, pass only where a GUI happens to be installed);
  · the tray shows something `/health` did not say → two owners of state;
  · «Open Zaelar» opens a remote address nobody handed it, or works only when the relay module exists;
  · the app's `Info.plist` loses its bundle id, `LSUIElement` or the folder-prompt sentences → a Dock icon, or a
    system prompt with no reason in it;
  · the release rename forgets the `.app` zip, or the installers stop parsing.

Disarms (each seen red): `daemon.cli` importing `daemon.tray` at the top → the headless-import test red; the model
reading anything but `/health` (the connected glyph without `ok`) → red; `LSUIElement` dropped from `info_plist.KEYS`
→ red; `Zaelar.zip` removed from `_RENAMES` → red.
"""
from __future__ import annotations

import importlib.util
import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
PACKAGING = ENGINE / "daemon" / "packaging"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the headless path never loads a GUI ───────────────────────────────────────────────────────────────────────

def test_python_m_daemon_imports_nothing_from_the_tray_or_a_gui_library(tmp_path):
    """Run in a FRESH interpreter, because this process has already imported half the suite: start the CLI's
    import path and a full `/health` render, then list what got loaded."""
    probe = (
        "import sys, json\n"
        "import daemon.__main__, daemon.cli, daemon.server, daemon.browser\n"
        "from daemon.http import routes\n"
        "routes.health(None, {})\n"
        "from daemon.browser import status; status.health_fields()\n"
        "bad = sorted(m for m in sys.modules if m.startswith(('daemon.tray', 'rumps', 'pystray', 'PIL', 'AppKit',"
        " 'objc', 'playwright')))\n"
        "print(json.dumps(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60, cwd=ENGINE,
                         env={"PATH": "/usr/bin:/bin", "ZAELAR_WORKSPACE": str(tmp_path), "PYTHONPATH": str(ENGINE),
                              "HOME": str(tmp_path)})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == [], \
        "the headless daemon imported a GUI or the browser driver at import time"


def test_the_tray_is_on_for_the_installed_program_and_off_for_python_m_daemon(monkeypatch):
    from daemon import cli
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cli._wants_tray(set()) is False, "python -m daemon (tests, self-host) runs headless"
    assert cli._wants_tray({"--tray"}) is True
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert cli._wants_tray(set()) is True, "the packaged program is the resident with its icon"
    assert cli._wants_tray({"--no-tray"}) is False, "CI starts the packaged program headless"


def test_a_finder_launch_argument_is_not_a_command():
    """Older macOS appends `-psn_0_12345` when a `.app` is opened from Finder; read as a command, it would print the
    usage text and exit instead of starting the daemon."""
    from daemon import cli
    words, flags = cli._split(["zaelar-daemon", "-psn_0_4711", "--no-tray"])
    assert words == ["zaelar-daemon"] and flags == {"--no-tray"}


# ── the tray is a view of /health ─────────────────────────────────────────────────────────────────────────────

def _health(**over):
    base = {"ok": True, "daemon": "zaelar", "version": "0.3.0", "configured": True,
            "capabilities": ["files.list", "browser.auth"],
            "browser": {"state": "ready", "channel": "chrome", "progress": 100, "size_mb": 0}}
    base.update(over)
    return base


LOCAL = {"enabled": True, "where": "local", "url": "http://localhost:43917", "reason": ""}
NOWHERE = {"enabled": False, "where": "", "url": "", "reason": "pair with your cloud agent first"}


def test_the_glyph_follows_health_and_nothing_else():
    from daemon.tray import model
    assert model.glyph(None) == "error"
    assert model.glyph({"daemon": "zaelar"}) == "error", "no `ok` from /health is not connected"
    assert model.glyph(_health()) == "connected"
    assert model.glyph(_health(configured=False)) == "waiting"
    assert model.glyph(_health(browser={"state": "downloading", "progress": 10})) == "waiting"


def test_the_menu_has_the_five_items_in_order():
    from daemon.tray import model
    v = model.view(_health(), LOCAL)
    assert [i.id for i in v.items] == ["status", "open", "folders", "signin", "egress", "updates", "quit"]
    assert v.items[0].enabled is False and "0.3.0" in v.items[0].label
    assert next(i for i in v.items if i.id == "signin").label == "Open sign-in window"
    assert next(i for i in model.view(_health(), LOCAL, "t1").items if i.id == "signin").label == \
        "Close sign-in window"


def test_open_zaelar_is_disabled_with_the_reason_when_there_is_nowhere_to_go():
    from daemon.tray import model
    item = next(i for i in model.view(_health(), NOWHERE).items if i.id == "open")
    assert item.enabled is False and item.tooltip == "pair with your cloud agent first"


def test_without_a_browser_the_menu_offers_the_download_and_while_it_runs_the_cancel():
    from daemon.tray import model
    absent = model.view(_health(browser={"state": "absent"}), LOCAL)
    assert "download_start" in [i.id for i in absent.items]
    running = model.view(_health(browser={"state": "downloading", "progress": 40, "size_mb": 171.0}), LOCAL)
    cancel = next(i for i in running.items if i.id == "download_cancel")
    assert "40%" in cancel.label and "171 MB" in cancel.label
    unsupported = model.view(_health(browser={"state": "unsupported"}), LOCAL)
    assert next(i for i in unsupported.items if i.id == "signin").enabled is False


def test_a_daemon_that_does_not_answer_offers_only_quit():
    from daemon.tray import model
    v = model.view(None, None)
    assert v.state == "error" and [i.id for i in v.items] == ["status", "quit"]


def test_the_menu_actions_call_the_daemons_own_functions(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config
    from daemon.tray.controller import Controller
    config.reset_cache()
    calls, notes = [], []

    class Windows:
        task = ""

        def current_task(self):
            return self.task

        def open_for_person(self):
            calls.append("open-window")
            self.task = "tray"

        def close(self, task):
            calls.append(f"close-{task}")
            self.task = ""

    class Job:
        def start(self):
            calls.append("download")

        def cancel(self):
            calls.append("cancel")

    class App:
        def open(self):
            calls.append("app")
            return {"ok": True}

    class Updater:
        # The real one reaches the network (`daemon.update.check`); its own tests live in
        # test_the_daemon_updates_itself_only_when_verified.py. Here only the wiring is under test.
        def check_and_download(self):
            calls.append("check")
            return {"ok": True, "current": {"version": "0.3.0", "build": 7}, "available": None, "state": "idle"}

        def install(self):
            calls.append("install")
            return {"state": "idle", "error": "", "restart": "launchd"}

    folder = tmp_path / "Docs"
    folder.mkdir()
    ctrl = Controller(1, notify=lambda t, m: notes.append(m), quit_fn=lambda: calls.append("quit"),
                      health_fn=lambda: _health(), target_fn=lambda: LOCAL, app=App(), windows=Windows(),
                      job=Job(), choose=lambda prompt: str(folder), updater=Updater())
    for item in ("open", "signin", "signin", "download_start", "download_cancel", "folders", "updates", "quit"):
        ctrl.act(item)
    assert calls == ["app", "open-window", "close-tray", "download", "cancel", "check", "quit"]
    assert str(folder.resolve()) in [str(Path(r).resolve()) for r in config.load()["roots"]], \
        "«Allowed folders…» grants through the permission circuit"
    assert any("0.3.0" in n and "up to date" in n for n in notes), "«Check for updates» says what the check found"
    config.reset_cache()


# ── «Open Zaelar» ─────────────────────────────────────────────────────────────────────────────────────────────

def test_open_zaelar_goes_to_the_local_engine_first_then_the_relay_then_nowhere():
    from daemon.browser import app_window
    assert app_window.target(probe=lambda u: True, relay=lambda: "https://x")["where"] == "local"
    remote = app_window.target(probe=lambda u: False, relay=lambda: "https://link.example/once")
    assert remote == {"enabled": True, "where": "remote", "url": "https://link.example/once", "reason": ""}
    assert app_window.target(probe=lambda u: False, relay=lambda: "") == {
        "enabled": False, "where": "", "url": "", "reason": "pair with your cloud agent first"}


def test_the_relay_link_is_read_lazily_and_its_absence_is_not_an_error():
    """The relay module is built by another change; until it exists this code must run unchanged."""
    from daemon.browser import app_window
    source = (ENGINE / "daemon" / "browser" / "app_window.py").read_text(encoding="utf-8")
    top = source.split("\ndef ", 1)[0]
    assert "relay" not in "\n".join(l for l in top.splitlines() if l.startswith(("import", "from"))), \
        "the relay is imported at module top"
    if importlib.util.find_spec("daemon.relay") is None:
        assert app_window._relay_link() == ""


def test_open_zaelar_reads_the_relays_one_time_link(monkeypatch):
    """The relay's `login_link()` answers `{"url", "expires_at"}` or None; only an https link is opened."""
    from daemon.browser import app_window
    relay = pytest.importorskip("daemon.relay.login_link")
    monkeypatch.setattr(relay, "login_link", lambda: {"url": "https://agent.example/once?t=1", "expires_at": "x"})
    assert app_window._relay_link() == "https://agent.example/once?t=1"
    monkeypatch.setattr(relay, "login_link", lambda: None)
    assert app_window._relay_link() == ""
    monkeypatch.setattr(relay, "login_link", lambda: {"url": "http://agent.example/once"})
    assert app_window._relay_link() == "", "a plain-http link from far away is not opened"


@pytest.mark.parametrize("raw,expected", [
    ("", "http://localhost:43917"),
    ("http://127.0.0.1:5000", "http://127.0.0.1:5000"),
    ("https://evil.example", "http://localhost:43917"),
    ("file:///etc/passwd", "http://localhost:43917"),
])
def test_the_local_engine_address_is_loopback_only(monkeypatch, raw, expected):
    from daemon.browser import app_window
    monkeypatch.setenv("ZAELAR_ENGINE_URL", raw)
    assert app_window.local_url() == expected


def test_the_app_window_is_one_window_in_app_mode_on_its_own_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon.browser import app_window
    launched = []

    class Proc:
        def poll(self):
            return None

    def popen(argv, **kw):
        launched.append(argv)
        return Proc()
    w = app_window.AppWindow(popen=popen, target_fn=lambda: LOCAL, exe_fn=lambda: "/c/chrome")
    assert w.open()["open"] is True
    assert w.open().get("already") is True and len(launched) == 1, "a second click does not open a second window"
    argv = launched[0]
    assert argv[0] == "/c/chrome" and "--app=http://localhost:43917" in argv
    profile = next(a for a in argv if a.startswith("--user-data-dir="))
    assert profile.endswith("app-profile"), profile


# ── packaging: the .app, its Info.plist, the release names, the installers ────────────────────────────────────

def test_the_info_plist_carries_the_bundle_id_the_menu_bar_flag_and_the_three_sentences(tmp_path):
    info = _load("daemon_info_plist_test", PACKAGING / "macos" / "info_plist.py")
    plist = tmp_path / "Info.plist"
    with open(plist, "wb") as fh:
        plistlib.dump({"CFBundleExecutable": "zaelar-daemon", "CFBundleIdentifier": "zaelar-daemon"}, fh)
    info.apply(plist, "9.9.9")
    with open(plist, "rb") as fh:
        data = plistlib.load(fh)
    assert data["CFBundleIdentifier"] == "com.zaelar.daemon"
    assert data["LSUIElement"] is True, "without it the daemon gets a Dock icon"
    assert data["CFBundleExecutable"] == "zaelar-daemon", "what PyInstaller wrote is kept"
    assert data["NSDocumentsFolderUsageDescription"] == \
        "Zaelar reads the documents in the folders you allow, to find or read them when you ask."
    assert data["NSDesktopFolderUsageDescription"] == \
        "Zaelar only looks at your Desktop if you allow it, to find what you ask for."
    assert data["NSDownloadsFolderUsageDescription"] == \
        "Zaelar reads your Downloads only if you allow it, to open or find what you downloaded."
    assert data["CFBundleShortVersionString"] == "9.9.9"


def test_the_mac_build_is_an_app_bundle_built_outside_the_release_folder():
    build = _load("daemon_build_test", PACKAGING / "build.py")
    assert build.APP_NAME == "Zaelar.app" and build.APP_ZIP == "Zaelar.zip"
    assert build.APP_DIST != build.DIST and build.DIST not in build.APP_DIST.parents, \
        "a release attaches every file in dist/daemon — a bundle is thousands"
    source = (PACKAGING / "build.py").read_text(encoding="utf-8")
    assert '"--onedir", "--windowed"' in source and '"--onefile", "--console"' in source
    assert '"--collect-data", "playwright"' in source, "the Node driver is data no import statement reveals"


def test_the_release_publishes_the_app_zip_under_a_per_architecture_name(tmp_path):
    names = _load("daemon_release_names_test", PACKAGING / "release_names.py")
    (tmp_path / "Zaelar.zip").write_bytes(b"app")
    (tmp_path / "zaelar-daemon.pyz").write_bytes(b"pyz")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    published = names.rename_for("macos-x86_64", tmp_path)
    assert sorted(p.name for p in published) == ["Zaelar-macos-x86_64.zip", "zaelar-daemon-macos-x86_64.pyz"]
    sums = (tmp_path / "SHA256SUMS-macos-x86_64").read_text(encoding="utf-8")
    assert "  Zaelar-macos-x86_64.zip\n" in sums


def test_the_screen_and_the_one_liner_ask_for_the_app_zip():
    from server.daemon_downloads import _ASSETS
    assert _ASSETS["macos"]["artifact"] == "Zaelar-macos.zip"
    get = (PACKAGING / "get.sh").read_text(encoding="utf-8")
    assert 'ASSET="Zaelar-$SUFFIX.zip"' in get
    assert 'ASSET="zaelar-daemon-$SUFFIX"' in get, "releases before the .app still install (the fallback)"


def test_the_installer_installs_the_app_and_hands_it_its_state_folder():
    text = (PACKAGING / "macos" / "install.sh").read_text(encoding="utf-8")
    assert 'APP="$PREFIX/Zaelar.app"' in text
    assert "ditto -x -k" in text, "the bundle is unpacked with ditto (symlinks and signature intact)"
    assert "<key>ZAELAR_WORKSPACE</key>" in text, "the app's program is not in bin/: its state folder is handed to it"
    assert "Interactive" in text
    assert 'rm -rf "$PREFIX/Zaelar.app"' in (PACKAGING / "macos" / "uninstall.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("script", ["macos/install.sh", "macos/uninstall.sh", "get.sh"])
def test_the_shell_installers_parse(script):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash")
    out = subprocess.run([bash, "-n", str(PACKAGING / script)], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr


def test_the_powershell_installers_are_parsed_on_windows_by_the_workflow():
    """No PowerShell where this suite runs; the artifacts workflow parse-checks every `.ps1` on its Windows runner."""
    workflow = (ENGINE / ".github" / "workflows" / "daemon-artifacts.yml").read_text(encoding="utf-8")
    assert "[System.Management.Automation.Language.Parser]::ParseFile" in workflow
    assert "daemon/packaging/windows/*.ps1" in workflow and "daemon/packaging/get.ps1" in workflow


def test_the_workflow_smoke_starts_the_app_headless_and_checks_the_browser():
    workflow = (ENGINE / ".github" / "workflows" / "daemon-artifacts.yml").read_text(encoding="utf-8")
    assert "Zaelar.app/Contents/MacOS/zaelar-daemon" in workflow and '"$BIN" --no-tray' in workflow
    assert "b['state']=='ready' and b['channel']=='chrome'" in workflow
    assert "browser.auth" in workflow and "evil.example" in workflow
    assert "h['unsupported_browsers']" in workflow and "$health.browser.state -ne 'ready'" in workflow
    assert "--ArgumentList '--no-tray'" not in workflow and "-ArgumentList '--no-tray'" in workflow
    assert "pip install -r daemon/requirements.txt -r daemon/packaging/requirements-build.txt" in workflow

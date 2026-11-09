"""The terminal side of the daemon.

Sub-commands exist for the things somebody needs from a terminal that the HTTP surface cannot give them: seeing
the token (to point an engine on the same machine at it), seeing what has been granted, changing it without a
UI, and replacing the token if it leaked.

    zaelar-daemon                 start it in the foreground
    zaelar-daemon status          is it running, on what port, with which folders
    zaelar-daemon token           print the API token
    zaelar-daemon rotate-token    mint a new one (the running daemon keeps the old until it restarts)
    zaelar-daemon allow PATH      grant a folder
    zaelar-daemon deny PATH       revoke one
    zaelar-daemon version         print the version and exit
    zaelar-daemon browser         where the browser stands (Chrome found · Chromium downloaded · neither)
    zaelar-daemon browser install download the Chromium now, with progress (only needed with no Google Chrome)

    --tray / --no-tray            with or without the menu-bar / notification-area icon. ON by default for the
                                  installed program, OFF for `python -m daemon` (the headless service tests run).

(`python -m daemon <command>` is the same thing when running from a source tree.)
"""
from __future__ import annotations

import json
import sys
import threading
import time

from . import PORT, VERSION, config, permissions, server
from .paths import audit_file, config_file, state_dir
from .permissions import Refusal

USAGE = __doc__


def _status() -> int:
    cfg = config.load()
    port = int(cfg.get("port") or PORT)
    print(json.dumps({
        "version": VERSION,
        "running": server.is_running(port),
        "port": port,
        "configured": bool(cfg.get("configured")),
        "roots": permissions.roots(),
        "state_dir": str(state_dir()),
        "config": str(config_file()),
        "audit": str(audit_file()),
    }, indent=1, ensure_ascii=False))
    return 0


def _allow_or_deny(command: str, argument: str) -> int:
    if not argument:
        print(f"usage: zaelar-daemon {command} /path/to/folder", file=sys.stderr)
        return 2
    try:
        roots = permissions.grant(argument) if command == "allow" else permissions.revoke(argument)
    except Refusal as refusal:
        print(refusal.message, file=sys.stderr)
        return 1
    # The change lands in daemon.json, which a RUNNING daemon has already cached in memory — say so rather than
    # let the user watch a granted folder stay invisible and conclude the permission system is broken.
    print("folders: " + (", ".join(roots) if roots else "(none)"))
    if server.is_running():
        print("the daemon is running: restart it for this to take effect.")
    return 0


def _wants_tray(flags: set[str]) -> bool:
    """`--tray` / `--no-tray` win; otherwise only the packaged program (PyInstaller sets `sys.frozen`) shows one."""
    if "--no-tray" in flags:
        return False
    if "--tray" in flags:
        return True
    return bool(getattr(sys, "frozen", False))


def _split(argv: list[str]) -> tuple[list[str], set[str]]:
    """Words and flags apart. `-psn_…` is the process serial number older macOS appends when a `.app` is opened
    from Finder — not an argument anybody typed, so it must not turn a start into the usage text."""
    words, flags = [], set()
    for arg in argv[1:]:
        if arg.startswith("-psn_"):
            continue
        (flags.add if arg.startswith("--") else words.append)(arg)
    return [argv[0] if argv else "zaelar-daemon", *words], flags


def _serve_with_tray() -> int:
    """The installed resident: the HTTP server on a thread, the tray on the main thread (macOS requires it).

    If a daemon is already answering on the port, this one leaves — two icons for one daemon would be two views
    arguing. If no tray can be shown here (no GUI library, no desktop), it simply serves headless."""
    port = server.resolve_port(None)
    if server.is_running(port):
        print(f"zaelar-daemon is already listening on 127.0.0.1:{port}", flush=True)
        return 0
    # ⚠️ THE SERVER BINDS BEFORE THE GUI LIBRARY LOADS. `http.server` resolves its own address once at bind
    # (`socket.getfqdn`, a reverse lookup), and inside the packaged `Zaelar.app` that lookup hung for as long as we
    # watched once AppKit had been loaded first (measured 2026-11-09: the HTTP thread parked in `mdns_hostbyaddr`,
    # `/health` never answering, the icon waiting forever). Bound first, the lookup is the plain process's.
    outcome: dict = {}
    thread = threading.Thread(target=lambda: outcome.setdefault("code", server.serve()), name="zaelar-http",
                              daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.is_running(port) and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.is_running(port):
        thread.join(timeout=1)
        return int(outcome.get("code", 1) or 1)
    from . import tray   # noqa: PLC0415 — the GUI never loads on the headless path
    runner, reason = tray.load()
    if runner is None:
        print(f"zaelar-daemon: no tray icon on this system ({reason}); running without one.", flush=True)
        thread.join()
        return int(outcome.get("code", 0) or 0)
    # First run with no Google Chrome: the Chromium download starts here, in the background, visible in the menu
    # (with Cancel) and in `/health`. A person who cancelled once is not asked again (`auto_download`).
    from .browser import status as browser_status   # noqa: PLC0415
    browser_status.ensure_download()
    from .tray.controller import Controller   # noqa: PLC0415
    return int(runner(Controller(port)) or 0)


def _browser(argument: str) -> int:
    from .browser import DOWNLOAD, status as browser_status   # noqa: PLC0415
    if argument == "install":
        current = browser_status.describe()
        if current["state"] in ("ready", "unsupported"):
            print(json.dumps(current, indent=1))
            return 0 if current["state"] == "ready" else 1
        DOWNLOAD.start()
        last = -1
        while DOWNLOAD.running:
            snap = DOWNLOAD.snapshot()
            if snap["progress"] != last:
                last = snap["progress"]
                print(f"  {last:3d}%  of {snap['size_mb']:.0f} MB", flush=True)
            time.sleep(0.2)
        final = browser_status.describe()
        print(json.dumps(final, indent=1))
        return 0 if final["state"] == "ready" else 1
    print(json.dumps(browser_status.health_fields(), indent=1))
    return 0


def main(argv: list[str]) -> int:
    argv, flags = _split(argv)
    command = (argv[1] if len(argv) > 1 else "").strip().lower()
    argument = argv[2] if len(argv) > 2 else ""

    if command in ("", "serve", "start", "run"):
        return _serve_with_tray() if _wants_tray(flags) else server.serve()

    if command == "browser":
        return _browser(argument.strip().lower())

    if command == "status":
        return _status()

    if command == "version":
        print(VERSION)
        return 0

    if command == "token":
        print(config.token())
        return 0

    if command in ("rotate-token", "rotate_token"):
        fresh = config.rotate_token()
        print(fresh)
        if server.is_running():
            print("the daemon is running: restart it so it starts accepting the new token.", file=sys.stderr)
        return 0

    if command in ("allow", "deny"):
        return _allow_or_deny(command, argument)

    print(USAGE, file=sys.stderr)
    return 2

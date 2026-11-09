"""The tray's brain, without a GUI: read `/health`, build the `View`, run what the person picked.

It reads `/health` over HTTP like any other client, rather than calling into the server's functions, so the icon
shows exactly what the engine sees — a daemon whose HTTP side died shows the error glyph even though this process
is still alive. The actions call the daemon's own functions in-process: the person clicking the menu IS the person
at this computer, the same standing the folder dialog has.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request

from .. import HOST, VERSION, audit
from ..browser import app_window
from ..browser.download import DOWNLOAD
from ..browser.window import WINDOWS
from ..fs import roots as folders
from ..fs.refusal import Refusal
from .. import picker
from . import model

POLL_S = 5.0


def read_health(port: int, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=timeout) as resp:   # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception:   # noqa: BLE001 — no answer is the error glyph, not an exception in the GUI loop
        return None


class _Updater:
    """The tray's door to `daemon.update`, imported when first used so the tray loads nothing it does not need."""

    def check_and_download(self) -> dict:
        from ..update import check   # noqa: PLC0415
        return check.check_and_download()

    def install(self) -> dict:
        from ..update import apply   # noqa: PLC0415
        return apply.install()


def update_message(result: dict) -> str:
    """One sentence for a check's result. Every refusal says the installed Zaelar was left untouched — it was."""
    current = (result.get("current") or {}).get("version") or VERSION
    available = result.get("available") or {}
    state = result.get("state")
    if result.get("note"):
        return f"You have Zaelar daemon {current} ({result['note']})."
    if state == "failed" or (not result.get("ok") and result.get("error")):
        return f"Update check failed: {result.get('error') or 'unknown error'}. Your Zaelar was not changed."
    if state == "ready" and available:
        return (f"Zaelar {available.get('version')} (build {available.get('build')}) is downloaded and verified. "
                "Choose «Install» in the menu to restart on it.")
    if available:
        return f"Zaelar {available.get('version')} (build {available.get('build')}) is available."
    return f"Zaelar daemon {current} is up to date."


class _Tray:
    """Stands in for the HTTP request a route receives: the caller is the person at this computer, via the menu."""

    @staticmethod
    def _caller() -> str:
        return "tray"


class Controller:
    """`notify(title, message)` and `quit_fn()` are supplied by the backend; everything else is injectable."""

    def __init__(self, port: int, notify=None, quit_fn=None, health_fn=None, target_fn=None,
                 app=None, windows=None, job=None, choose=None, updater=None):
        self.port = port
        self._notify = notify or (lambda title, message: None)
        self._quit = quit_fn or (lambda: os._exit(0))
        self._health = health_fn or (lambda: read_health(self.port))
        self._target = target_fn or app_window.target
        self._app = app or app_window.APP
        self._windows = windows or WINDOWS
        self._job = job or DOWNLOAD
        self._choose = choose or picker.choose_folder
        self._updater = updater or _Updater()
        self._lock = threading.Lock()
        self._view = model.view(None, None)

    # ── reading ────────────────────────────────────────────────────────────────────────────────────────────

    def _egress(self) -> dict | None:
        try:
            from .. import config   # noqa: PLC0415
            from ..egress import tunnel   # noqa: PLC0415
            return {"enabled": config.egress_enabled(), "connected": tunnel.TUNNEL.connected()}
        except Exception as e:   # noqa: BLE001 — an unreadable state greys the item out, never the menu
            from ..egress import note   # noqa: PLC0415
            note("tray could not read the tunnel state", e)
            return None

    def refresh(self) -> model.View:
        health = self._health()
        target = self._target() if health else None
        v = model.view(health, target, self._windows.current_task(), self._egress() if health else None)
        with self._lock:
            self._view = v
        return v

    def view(self) -> model.View:
        with self._lock:
            return self._view

    def start_polling(self) -> None:
        """Re-read `/health` every `POLL_S` on a thread of its own: a slow answer must never freeze the menu bar,
        whose own timer only renders the last `view()`."""
        def loop():
            stop = threading.Event()
            while not stop.wait(POLL_S):
                self.refresh()
        self.refresh()
        threading.Thread(target=loop, name="tray-health", daemon=True).start()

    # ── acting ─────────────────────────────────────────────────────────────────────────────────────────────

    def act(self, item_id: str) -> None:
        """Run one menu item. Runs on a worker thread (`act_async`): a folder dialog or a browser launch must never
        freeze the menu bar."""
        handler = getattr(self, f"_do_{item_id}", None)
        if handler is None:
            return
        try:
            handler()
        except Refusal as refusal:
            self._notify("Zaelar", refusal.message)
        except Exception as e:   # noqa: BLE001 — the tray stays up; the person sees what failed
            self._notify("Zaelar", f"That did not work: {type(e).__name__}.")
        finally:
            self.refresh()

    def act_async(self, item_id: str) -> None:
        threading.Thread(target=self.act, args=(item_id,), name=f"tray-{item_id}", daemon=True).start()

    def _do_open(self) -> None:
        out = self._app.open()
        if out.get("already"):
            self._notify("Zaelar", "Zaelar is already open.")

    def _do_folders(self) -> None:
        chosen = self._choose("Choose a folder Zaelar may read")
        if not chosen:
            return
        folders.grant(chosen)
        audit.record("permissions.grant", caller="tray", path=chosen, outcome="ok")
        self._notify("Zaelar", f"Zaelar can now read {chosen}.")

    def _do_signin(self) -> None:
        task = self._windows.current_task()
        if task:
            self._windows.close(task)
        else:
            self._windows.open_for_person()

    def _do_download_start(self) -> None:
        from .. import config   # noqa: PLC0415
        config.save_browser(auto_download=True)
        self._job.start()

    def _do_download_cancel(self) -> None:
        self._job.cancel()

    def _do_egress(self) -> None:
        """Flip the outbound tunnel through the daemon's own route (`POST /egress`), as the person at this computer:
        the menu item said what it means, and choosing it is his consent."""
        from ..http import routes   # noqa: PLC0415
        on = not bool((self._egress() or {}).get("enabled"))
        routes.egress_switch(_Tray(), {"enabled": on, "consent": on})
        self._notify("Zaelar", "Outbound tunnel on: your cloud agent browses through this computer." if on
                     else "Outbound tunnel off.")

    def _do_updates(self) -> None:
        """Check now; when a newer, VERIFIED release exists, download and verify it — then say what happened. The
        install itself is a second, explicit click (`update_install`), because it restarts the daemon."""
        result = self._updater.check_and_download()
        self._notify("Zaelar", update_message(result))

    def _do_update_install(self) -> None:
        out = self._updater.install()
        if out.get("error"):
            self._notify("Zaelar", f"The update was not installed: {out['error']}. Zaelar was left as it was.")
        elif out.get("restart") == "manual":
            self._notify("Zaelar", f"Zaelar {out.get('installed', 'update')}. Quit and open Zaelar to finish.")

    def _do_quit(self) -> None:
        audit.record("daemon.stop", outcome="ok", detail={"by": "tray"})
        self._quit()

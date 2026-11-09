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


class Controller:
    """`notify(title, message)` and `quit_fn()` are supplied by the backend; everything else is injectable."""

    def __init__(self, port: int, notify=None, quit_fn=None, health_fn=None, target_fn=None,
                 app=None, windows=None, job=None, choose=None):
        self.port = port
        self._notify = notify or (lambda title, message: None)
        self._quit = quit_fn or (lambda: os._exit(0))
        self._health = health_fn or (lambda: read_health(self.port))
        self._target = target_fn or app_window.target
        self._app = app or app_window.APP
        self._windows = windows or WINDOWS
        self._job = job or DOWNLOAD
        self._choose = choose or picker.choose_folder
        self._lock = threading.Lock()
        self._view = model.view(None, None)

    # ── reading ────────────────────────────────────────────────────────────────────────────────────────────

    def refresh(self) -> model.View:
        health = self._health()
        target = self._target() if health else None
        v = model.view(health, target, self._windows.current_task())
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

    def _do_updates(self) -> None:
        health = self._health() or {}
        version = health.get("version") or VERSION
        self._notify("Zaelar", f"You have Zaelar daemon {version}. Automatic updates are not available yet.")

    def _do_quit(self) -> None:
        audit.record("daemon.stop", outcome="ok", detail={"by": "tray"})
        self._quit()

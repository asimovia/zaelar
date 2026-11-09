"""The macOS menu-bar extra, on `rumps` (a thin layer over AppKit through PyObjC).

AppKit runs on the MAIN thread, so this owns it: the HTTP server runs on a thread of its own (`daemon.cli`), the
controller polls `/health` on another, and a `rumps.Timer` on the main thread renders the last view and shows the
notifications the worker threads queued. Nothing here touches AppKit from any other thread.

No Dock icon: the packaged `Zaelar.app` carries `LSUIElement` in its `Info.plist` (`packaging/macos/info_plist.py`),
so the menu bar is the whole of its presence. Run from source, a Python process gets a Dock icon anyway — the tray
is for the installed resident.
"""
from __future__ import annotations

import collections

import rumps   # noqa: I001 — imported only through `daemon.tray.load()`, never by the headless service

from . import icons
from .controller import Controller

_RENDER_S = 1.0


class _MenuBar(rumps.App):
    def __init__(self, ctrl: Controller, notes: collections.deque):
        super().__init__("Zaelar", icon=icons.path("waiting", template=True), template=True, quit_button=None)
        self._ctrl, self._notes, self._shown = ctrl, notes, None
        self._timer = rumps.Timer(self._tick, _RENDER_S)
        self._timer.start()
        self._tick(None)

    def _tick(self, _timer) -> None:
        while self._notes:
            title, message = self._notes.popleft()
            try:
                rumps.notification(title, "", message)
            except Exception:   # noqa: BLE001 — no notification centre (unbundled run): the menu still works
                pass
        view = self._ctrl.view()
        key = (view.state, tuple(view.items))
        if key == self._shown:
            return
        self._shown = key
        self.icon = icons.path(view.state, template=True)
        self.menu.clear()
        entries = []
        for item in view.items:
            entry = rumps.MenuItem(item.label, callback=self._callback(item.id) if item.enabled else None)
            if item.tooltip:
                try:
                    entry._menuitem.setToolTip_(item.tooltip)   # rumps has no tooltip API; AppKit does
                except Exception:   # noqa: BLE001
                    pass
            entries.append(entry)
            if item.id == "status":
                entries.append(rumps.separator)
        self.menu = entries

    def _callback(self, item_id: str):
        return lambda _sender: self._ctrl.act_async(item_id)


def run(ctrl: Controller) -> int:
    notes: collections.deque = collections.deque(maxlen=8)
    ctrl._notify = lambda title, message: notes.append((title, message))
    quit_after = ctrl._quit

    def quit_app():
        try:
            rumps.quit_application()
        finally:
            quit_after()
    ctrl._quit = quit_app
    ctrl.start_polling()
    _MenuBar(ctrl, notes).run()
    return 0

"""The Windows notification-area icon, on `pystray` + `Pillow` (pystray also draws one on Linux desktops that have a
tray). Glyph AND colour per state: Windows does not tint tray icons, so the colour is free to help.

pystray rebuilds the menu from a callable every time it opens, so the menu is always the controller's last view; a
thread re-renders the icon and the hover title when the state changes. A disabled item cannot carry a tooltip here,
so its reason goes into the label.

THE CONSOLE WINDOW. The `.exe` is a console program on purpose — `zaelar-daemon status` in a terminal must print —
so started at logon by the scheduled task it would also open a console nobody asked for. When this process is the
ONLY one attached to its console (started by the task, not from a terminal someone is typing in), the tray hides it.
"""
from __future__ import annotations

import sys
import threading

import pystray   # noqa: I001 — imported only through `daemon.tray.load()`, never by the headless service
from PIL import Image

from . import icons
from .controller import Controller


def _hide_own_console() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes   # noqa: PLC0415
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return
        attached = (ctypes.c_uint * 4)()
        if kernel32.GetConsoleProcessList(attached, 4) <= 1:
            ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
    except Exception:   # noqa: BLE001 — a visible console is ugly, not broken
        pass


def _image(state: str):
    return Image.open(icons.path(state, template=False))


def run(ctrl: Controller) -> int:
    _hide_own_console()

    def entries():
        out = []
        for item in ctrl.view().items:
            label = item.label if item.enabled or not item.tooltip else f"{item.label} — {item.tooltip}"
            out.append(pystray.MenuItem(label, (lambda iid: lambda _icon, _item: ctrl.act_async(iid))(item.id),
                                        enabled=item.enabled))
            if item.id == "status":
                out.append(pystray.Menu.SEPARATOR)
        return out

    first = ctrl.view()
    icon = pystray.Icon("Zaelar", _image(first.state), first.title, menu=pystray.Menu(lambda: entries()))
    ctrl._notify = lambda title, message: icon.notify(message, title)
    quit_after = ctrl._quit

    def quit_app():
        try:
            icon.stop()
        finally:
            quit_after()
    ctrl._quit = quit_app

    def render():
        shown = None
        stop = threading.Event()
        while not stop.wait(1.0):
            view = ctrl.view()
            if view.state != shown:
                shown = view.state
                try:
                    icon.icon = _image(view.state)
                except Exception:   # noqa: BLE001
                    pass
            icon.title = view.title
            try:
                icon.update_menu()
            except Exception:   # noqa: BLE001
                pass

    ctrl.start_polling()
    threading.Thread(target=render, name="tray-render", daemon=True).start()
    icon.run()
    return 0

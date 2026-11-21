"""The SIGN-IN HANDOFF: the operator's account is not ours, so anything that needs it works one way only — open the
site's real login window, let him type, and carry on from there. Two moments, one each way: `start()` opens the
window, `finish()` tells the task waiting on it that he is in. Credentials are never typed by us.

The conversation host's `sign_in(site, done)` act reaches both (`conversation_host/acts_tasks._sign_in`); `start` is
the `web.login` consequence door. The order goes to the browser widget's owner through its supervised mailbox
(`widgets/supervisor.enqueue`): the owner is the only writer of its store.
"""
from __future__ import annotations

import logging

from nucleo import consequence as _consequence

logger = logging.getLogger("zaelar.web_login")


def _emit(label: str, text: str = "", **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, text=text[:200], role="system", extra=extra or None)
    except Exception as e:  # noqa: BLE001 — a trace that cannot be written never stops the handoff
        logger.debug(f"web_login: {label} not emitted — {e!r}")


def _enqueue(action: str, payload: dict) -> bool:
    try:
        from widgets import supervisor
        return supervisor.enqueue("navegador", action, payload)
    except Exception as e:  # noqa: BLE001 — the card stays, and its own button can still carry the order
        logger.warning(f"web_login: {action} not queued to the browser — {e!r}")
        return False


@_consequence.door("web.login", neutral="dry")
def start(site: str) -> str:
    """Open the REAL browser window so the operator can sign in to `site`. Returns the task id, or "".

    Creates the task card, shows it, and queues `authenticate` to the browser owner; the owner relaunches headed
    and returns to headless once the session is in the profile. Without a site there is NOTHING to open and we do
    not guess (a 2026-07-23 bug defaulted to a site nobody asked for)."""
    site = (site or "").strip()
    if not site:
        return ""
    try:
        from widgets.navegador import tasks as navtasks
        url = site if site.startswith("http") else f"https://{site.lstrip('/')}"
        task_id = navtasks.create(f"Iniciar sesión · {site}", title=f"Login · {site}")
        _emit("widget_show_hint", site, id=navtasks.inst_id(task_id))
        try:
            from voice.observer import emit as _emit_raw
            _emit_raw("widget", "show", extra={"id": navtasks.inst_id(task_id), "src": "flash"})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"web_login: the card was not shown — {e!r}")
        _enqueue("authenticate", {"task_id": task_id, "url": url})
        _emit("🔐 abriendo ventana de inicio de sesión", site)
        return task_id
    except Exception as e:  # noqa: BLE001
        logger.warning(f"web_login: the sign-in window was not opened — {e}")
        return ""


def finish(channel: str = "") -> str:
    """He says he is signed in → queue `auth_done` to the task that was waiting. Returns its id, or "" when nothing
    was waiting (the honest answer, instead of promising to carry on). Same outcome as the card's button."""
    try:
        from widgets.navegador import tasks as navtasks
        tid = navtasks.login_waiting_id()
        if not tid:
            _emit("⚠️ login_done sin login pendiente")
            return ""
        _enqueue("auth_done", {"task_id": tid})
        _emit(f"🔓 login confirmado{(' por ' + channel) if channel else ''}", tid)
        return tid
    except Exception as e:  # noqa: BLE001
        logger.warning(f"web_login: the sign-in was not confirmed — {e}")
        return ""

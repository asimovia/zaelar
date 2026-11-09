"""A relayed `command` → the SAME handler the loopback route runs → one `result` frame.

The relay carries the loopback route table as framed requests: `files.list` is `/files/list`, `browser.open` is
`/browser/open`, and so on, through the very functions in `daemon/http/routes.py` — one boundary, two transports. What
is different about a REMOTE caller is applied here, before the handler, and nowhere else:

  · `profile` is DROPPED from `browser.open`. A local engine may name its own profile directory; a caller across the
    internet names no directory on his disk. The window opens on the daemon's own profile, always.
  · An op not in `OPS` is an error result (`unknown_op`), never a guess.
  · `deadline_ms` is honoured: the handler runs on a worker thread and the result is `deadline_exceeded` once it
    passes (clamped to `MAX_DEADLINE_MS`, the contract's ceiling).
  · A result bigger than `MAX_RESULT_BYTES` is refused (`result_too_large`) rather than cut.
  · Every relayed operation is audited with `caller: relay`, so «what did the cloud agent read?» has an answer.
"""
from __future__ import annotations

import json
import re
import threading

from .. import VERSION, audit
from ..fs.refusal import Refusal

MAX_RESULT_BYTES = 20 * 1024 * 1024
MAX_DEADLINE_MS = 120_000
DEFAULT_DEADLINE_MS = 30_000
#: `browser.open` answers as soon as the window is launching (the contract: the engine then polls `browser.state`).
OPEN_WAIT_S = 5.0

# A sign-in or registration page by its URL, in the languages the product speaks — the daemon's own conservative read
# for `signed_in` (the engine applies its own, richer judgement on the same URL and count).
_LOGIN_URL_RE = re.compile(r"log[-_ ]?in|sign[-_ ]?(in|up|on)|auth|sso|oauth|register|registr|iniciar|entrar|acceso|"
                           r"inscri|password|contrase", re.I)


class _RelayCaller:
    """Stands in for the HTTP request the handlers receive: they only ask it who the caller is."""

    @staticmethod
    def _caller() -> str:
        return "relay"


_CALLER = _RelayCaller()


def _routes():
    from ..http import routes
    return routes


def _windows():
    from .. import browser
    return browser.WINDOWS


def _current_task() -> str:
    return str((getattr(_windows(), "_current", None) or {}).get("task") or "")


def _text(args: dict, key: str) -> str:
    v = args.get(key)
    return v if isinstance(v, str) else ""


def signed_in(state: dict) -> bool:
    """Off any sign-in/registration page AND at least one new cookie since the window opened."""
    url = str(state.get("url") or "")
    return bool(state.get("open")) and bool(url) and not _LOGIN_URL_RE.search(url) and \
        int(state.get("new_cookies") or 0) >= 1


# ── the ops ──────────────────────────────────────────────────────────────────────────────────────────────────

def _files_list(args: dict) -> dict:
    return _routes().list_dir(_CALLER, {"path": _text(args, "path"), "limit": args.get("limit")})


def _files_read(args: dict) -> dict:
    return _routes().read_file(_CALLER, {"path": _text(args, "path"), "max_bytes": args.get("max_bytes")})


def _files_search(args: dict) -> dict:
    return _routes().search(_CALLER, {"query": _text(args, "query"), "path": _text(args, "under") or _text(args, "path"),
                                      "content": bool(args.get("content")), "limit": args.get("limit")})


def strip_remote(args: dict) -> dict:
    """What a remote caller may pass to `browser.open`: the URL and the task. `profile` never crosses."""
    return {"url": _text(args, "url"), "task": _text(args, "task_id") or _text(args, "task")}


def _browser_open(args: dict) -> dict:
    payload = strip_remote(args)
    box: dict = {}

    def run():
        try:
            box["out"] = _routes().browser_open(_CALLER, payload)
        except Refusal as r:
            box["refusal"] = r
        except Exception as e:  # noqa: BLE001
            box["error"] = e
    t = threading.Thread(target=run, name="relay-browser-open", daemon=True)
    t.start()
    t.join(OPEN_WAIT_S)
    if "refusal" in box:
        raise box["refusal"]
    if "error" in box:
        raise box["error"]
    return {"ok": True, "opened": True, "launching": t.is_alive()}


def _browser_state(args: dict) -> dict:
    task = _text(args, "task_id") or _text(args, "task") or _current_task()
    state = dict(_routes().browser_state(_CALLER, {"task": task}))
    state["signed_in"] = signed_in(state)
    return state


def _browser_close(args: dict) -> dict:
    task = _text(args, "task_id") or _text(args, "task") or _current_task()
    _routes().browser_close(_CALLER, {"task": task})
    return {"ok": True, "closed": True}


def _export_session(args: dict) -> dict:
    from . import session_export
    return session_export.export(_text(args, "site"))


def _daemon_status(_args: dict) -> dict:
    from ..fs import roots as folders
    routes = _routes()
    return {"ok": True, "version": VERSION, "caps": routes.capabilities(), "roots_count": len(folders.roots()),
            "browser": {"open": bool(getattr(_windows(), "_current", None))}}


OPS = {
    "files.list": _files_list,
    "files.read": _files_read,
    "files.search": _files_search,
    "browser.open": _browser_open,
    "browser.state": _browser_state,
    "browser.close": _browser_close,
    "browser.export_session": _export_session,
    "daemon.status": _daemon_status,
}


def _error(cid: str, code: str, message: str) -> dict:
    return {"t": "result", "id": cid, "ok": False, "error": {"code": code, "message": message}}


def _deadline_s(raw) -> float:
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        ms = DEFAULT_DEADLINE_MS
    return max(1, min(ms, MAX_DEADLINE_MS)) / 1000.0


def handle(frame: dict) -> dict:
    """One `command` frame in, its `result` frame out. Never raises."""
    cid = str(frame.get("id") or "")
    op = str(frame.get("op") or "")
    args = frame.get("args") if isinstance(frame.get("args"), dict) else {}
    fn = OPS.get(op)
    if fn is None:
        audit.record("relay.command", caller="relay", outcome="refused", reason="unknown_op", detail={"op": op[:64]})
        return _error(cid, "unknown_op", f"This daemon has no operation {op[:64]!r}.")
    box: dict = {}

    def run():
        try:
            box["data"] = fn(args)
        except Refusal as r:
            box["refusal"] = r
        except Exception as e:  # noqa: BLE001 — the text stays in the audit log, never in the answer
            box["error"] = e
    worker = threading.Thread(target=run, name=f"relay-{op}", daemon=True)
    worker.start()
    worker.join(_deadline_s(frame.get("deadline_ms")))
    if worker.is_alive():
        audit.record(op, caller="relay", outcome="refused", reason="deadline_exceeded")
        return _error(cid, "deadline_exceeded", "The operation did not finish within its deadline.")
    if "refusal" in box:
        r = box["refusal"]
        audit.record(op, caller="relay", outcome="refused", reason=r.code)
        return _error(cid, r.code, r.message)
    if "error" in box:
        e = box["error"]
        audit.record(op, caller="relay", outcome="error", reason=type(e).__name__, detail={"message": str(e)[:400]})
        return _error(cid, "internal", "Something went wrong on the daemon; the details are in its log.")
    data = box.get("data") if isinstance(box.get("data"), dict) else {}
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return _error(cid, "internal", "The result could not be encoded.")
    if size > MAX_RESULT_BYTES:
        audit.record(op, caller="relay", outcome="refused", reason="result_too_large", detail={"bytes": size})
        return _error(cid, "result_too_large", "The result is bigger than what one answer carries.")
    return {"t": "result", "id": cid, "ok": True, "data": data}

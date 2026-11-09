"""The route table, and one small function per route.

Each handler takes `(request, payload)` and returns the dict that becomes the JSON body. Raising `Refusal` is
how a route says no with a reason; anything else raising is a bug, and the HTTP layer turns it into a 500 whose
text the caller never sees.

EVERY NUMBER OFF THE WIRE IS COERCED, NEVER TRUSTED. `int(payload["limit"])` on `{"limit": "lots"}` raises
inside the handler, which the layer above turns into a 500 — an internal-error status for what is really a bad
argument, and a stack frame's worth of noise in the log every time an agent guesses a field name wrong. `_as_int`
clamps instead, so a nonsense value behaves like an absent one.
"""
from __future__ import annotations

from .. import VERSION, audit, config
from ..fs import listing, reading, searching
from .. import picker
from .. import browser
from .. import update
from ..fs import roots as folders
from ..fs.entries import LIST_DEFAULT_LIMIT, LIST_MAX_LIMIT, MAX_READ_BYTES

# What the engine may ask for. A capability the engine believes in is a promise to the user, so nothing appears
# here until it is really there: offering a browser hand-off the daemon cannot perform makes the agent tell the
# user it will open a window and then not.
CAPABILITIES = ["files.list", "files.read", "files.search"]


def capabilities() -> list[str]:
    """What this daemon can do RIGHT NOW: the files half always, the sign-in window only when a browser is really
    there to open (`daemon.browser.available()`) — P2's capability is measured, never declared by hand — and the
    outbound tunnel (`egress`, V2-836) only while the person has it switched on."""
    return list(CAPABILITIES) + ([browser.CAPABILITY] if browser.available() else []) + \
        ([EGRESS_CAPABILITY] if config.egress_enabled() else [])


EGRESS_CAPABILITY = "egress"

AUDIT_DEFAULT_LIMIT = 200
AUDIT_MAX_LIMIT = 1_000


def _as_int(payload: dict, key: str, default: int, lo: int, hi: int) -> int:
    """A number from the wire, clamped into a range it cannot leave. Anything unreadable becomes the default."""
    raw = payload.get(key)
    if raw is None or isinstance(raw, bool):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(value, hi))


def _as_text(payload: dict, key: str) -> str:
    raw = payload.get(key)
    return raw if isinstance(raw, str) else ""


# ── the routes ────────────────────────────────────────────────────────────────────────────────────────────

def health(_request, _payload: dict) -> dict:
    """Deliberately says nothing about the user. It is the only route reachable without the token, so what it
    reveals is what an unauthenticated caller on this machine may learn: that a daemon is here, and what it can
    do."""
    cfg = config.load()
    return {
        "ok": True,
        "daemon": "zaelar",
        "version": VERSION,
        "configured": bool(cfg.get("configured")),
        "capabilities": capabilities(),
        **browser.health_fields(),
        **update.health_fields(),
    }


def permissions(_request, _payload: dict) -> dict:
    cfg = config.load()
    return {"ok": True, "roots": folders.roots(), "configured": bool(cfg.get("configured")),
            "candidates": folders.candidates()}


def grant(request, payload: dict) -> dict:
    path = _as_text(payload, "path")
    granted = folders.grant(path)
    audit.record("permissions.grant", caller=request._caller(), path=path, outcome="ok")
    return {"ok": True, "roots": granted}


def pick(request, payload: dict) -> dict:
    """Open the system's folder dialog on this desktop and grant what the person chose — through `grant`, so the
    same boundary holds. A cancel is not a refusal: `cancelled` and the allowlist unchanged."""
    path = picker.choose_folder(_as_text(payload, "prompt"))
    if not path:
        return {"ok": False, "cancelled": True, "roots": folders.roots()}
    granted = folders.grant(path)
    audit.record("permissions.pick", caller=request._caller(), path=path, outcome="ok")
    return {"ok": True, "roots": granted, "path": path}


def revoke(request, payload: dict) -> dict:
    path = _as_text(payload, "path")
    remaining = folders.revoke(path)
    audit.record("permissions.revoke", caller=request._caller(), path=path, outcome="ok")
    return {"ok": True, "roots": remaining}


def list_dir(request, payload: dict) -> dict:
    limit = _as_int(payload, "limit", LIST_DEFAULT_LIMIT, 1, LIST_MAX_LIMIT)
    out = listing.list_dir(_as_text(payload, "path") or None, limit=limit)
    audit.record("files.list", caller=request._caller(), path=out.get("path"), outcome="ok",
                 detail={"entries": len(out.get("entries") or [])})
    return out


def read_file(request, payload: dict) -> dict:
    cap = _as_int(payload, "max_bytes", MAX_READ_BYTES, 1, MAX_READ_BYTES)
    out = reading.read_file(_as_text(payload, "path"), max_bytes=cap)
    audit.record("files.read", caller=request._caller(), path=out.get("path"), outcome="ok",
                 detail={"bytes": len(out.get("text") or ""), "truncated": bool(out.get("truncated"))})
    return out


def search(request, payload: dict) -> dict:
    limit = _as_int(payload, "limit", 100, 1, searching.SEARCH_MAX_LIMIT)
    out = searching.search(_as_text(payload, "query"), raw_path=_as_text(payload, "path") or None,
                           content=bool(payload.get("content")), limit=limit)
    audit.record("files.search", caller=request._caller(), path=_as_text(payload, "path") or None, outcome="ok",
                 detail={"query": out.get("query"), "hits": len(out.get("hits") or []),
                         "stopped_early": out.get("stopped_early")})
    return out


def read_audit(_request, payload: dict) -> dict:
    """Reading the log is not itself logged: it is the one operation whose record would be pure noise, and a log
    that records reads of itself grows without anybody doing anything."""
    limit = _as_int(payload, "limit", AUDIT_DEFAULT_LIMIT, 1, AUDIT_MAX_LIMIT)
    return {"ok": True, "entries": audit.tail(limit)}


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit
    return (urlsplit(url or "").hostname or "")[:200]


def browser_open(request, payload: dict) -> dict:
    """Open the sign-in window on this screen. The audit keeps the HOST, never the full address: a login URL can
    carry a one-time code in its query."""
    url = _as_text(payload, "url")
    out = browser.WINDOWS.open(_as_text(payload, "task"), url, _as_text(payload, "profile"))
    audit.record("browser.open", caller=request._caller(), path=_host_of(url), outcome="ok")
    return out


def browser_state(_request, payload: dict) -> dict:
    """Polled by the engine while it waits: the URL and how many cookies appeared — never which ones."""
    return browser.WINDOWS.state(_as_text(payload, "task"))


def browser_close(request, payload: dict) -> dict:
    out = browser.WINDOWS.close(_as_text(payload, "task"))
    audit.record("browser.close", caller=request._caller(), path=None, outcome="ok")
    return out


def egress_state(_request, _payload: dict) -> dict:
    """The tunnel as this computer sees it: the switch, when he consented, and what it is carrying."""
    from ..egress import tunnel
    section = config.egress()
    return {"ok": True, "enabled": bool(section.get("enabled")), "consented_at": section.get("consented_at"),
            **tunnel.TUNNEL.view()}


def egress_switch(request, payload: dict) -> dict:
    """Switch the tunnel. ON needs `consent: true` — the screen on this computer showed the text and he pressed
    «I understand, turn it on» — and is refused to anything that says it came through the relay: a remote command
    never flips this switch. OFF is immediate and closes every stream."""
    from ..egress import tunnel
    from ..fs.refusal import Refusal
    enabled = payload.get("enabled") is True
    if enabled and request._caller() == "relay":
        raise Refusal("not_local", "The tunnel is switched on only from this computer.")
    try:
        section = tunnel.switch(enabled, consent=payload.get("consent") is True)
    except ValueError:
        raise Refusal("consent_required", "Turning the tunnel on needs your consent on this computer.") from None
    audit.record("egress.switch", caller=request._caller(), outcome="ok", detail={"enabled": section["enabled"]})
    return egress_state(request, {})


TABLE: dict[tuple[str, str], object] = {
    ("GET", "/health"): health,
    ("GET", "/permissions"): permissions,
    ("POST", "/permissions/grant"): grant,
    ("POST", "/permissions/revoke"): revoke,
    ("POST", "/permissions/pick"): pick,
    ("POST", "/files/list"): list_dir,
    ("POST", "/files/read"): read_file,
    ("POST", "/files/search"): search,
    ("POST", "/audit"): read_audit,
    ("POST", "/browser/open"): browser_open,
    ("POST", "/browser/state"): browser_state,
    ("POST", "/browser/close"): browser_close,
    ("GET", "/egress"): egress_state,
    ("POST", "/egress"): egress_switch,
}

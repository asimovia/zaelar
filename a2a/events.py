"""Observability of the A2A network: every op is declared ONCE here (OPS) and every step emits exactly one row.

Row shape: ``{kind: "a2a", family: "a2a", op, rel, cid, peer, dir, ok, ms, trace, label, ...fields}``.
Guards applied to every row (I10, the privacy half): `peer` is the first 8 chars of the peer key, never a full
peer DID; no field may hold a 64/32-hex hash, a signature or an outside text longer than EXCERPT.

Sinks: tests and the lab add their own with `add_sink`; the engine sink (the observability stream) is attached by `attach_bus()`,
which the engine calls at boot (post-clean wiring). Emission never raises (I6).
"""
from __future__ import annotations

import collections
import re
import time
from typing import Callable

from .identity import short

EXCERPT = 160

# op → extra fields it may carry (beyond the common ones). The table in docs/modules/zaelar-a2a.md mirrors it.
OPS: dict[str, tuple[str, ...]] = {
    "key_created": ("did", "agent_id"),
    "registered": ("agent_id", "roster"),
    "heartbeat": ("roster_state",),
    "pull": ("n", "cursor_from", "cursor_to", "reason", "status"),
    "beat": ("pulls", "empty", "avg_ms", "max_ms"),
    "wake": ("sig_ok", "wake_kind"),
    "publish": ("hashes",),
    "discover": ("trigger", "hashes", "matches", "matched_by"),
    "propose": ("matched_by", "batch"),
    "propose_answer": ("answer",),
    "request": ("matched_by", "crossing", "excerpt"),
    "request_card": ("answer",),
    "accept": ("scopes", "crossing"),
    "decline": ("declined_until",),
    "disconnect": (),
    "explain": ("lang",),
    "grant": ("item", "verbs", "audience", "expires_at", "how"),
    "revoke": ("item", "audience"),
    "grant_notice": ("item", "verbs", "expires_at"),
    "msg": ("len", "shown", "excerpt"),
    "msg_blocked": ("reason",),
    "query": ("item", "projection", "args"),
    "reply": ("item", "projection", "n", "fields"),
    "denied": ("item", "reason"),
    "live_open": ("item", "share", "ttl_s"),
    "live_sample": ("share", "seq"),
    "live_read": ("share", "n", "closed"),
    "live_close": ("share",),
    "dropped": ("reason", "envelope_kind"),
    "send_failed": ("status", "envelope_kind"),
    "error": ("where", "exc_class"),
}

COMMON = ("op", "rel", "cid", "peer", "dir", "ok", "ms", "trace", "label")
_HEX = re.compile(r"\b[0-9a-f]{32,}\b")
_DID = re.compile(r"did:key:[A-Za-z0-9+/=_-]{20,}")

_sinks: list[Callable[[dict], None]] = []
_recent: "collections.deque[dict]" = collections.deque(maxlen=200)   # the last rows, for the Network view and voice
_label_names: dict[str, str] = {}      # cid → display name, for labels


def add_sink(fn: Callable[[dict], None]) -> None:
    _sinks.append(fn)


def remove_sink(fn: Callable[[dict], None]) -> None:
    if fn in _sinks:
        _sinks.remove(fn)


def attach_bus() -> None:
    """Route rows to the engine's observability stream (kind `a2a`, family `a2a`, piece `a_mail`) — the one stream
    the local viewer and the bus log read. Called by the engine at boot; idempotent."""
    if any(getattr(s, "_a2a_bus", False) for s in _sinks):
        return

    def _bus(row: dict) -> None:
        from voice import observer
        extra = {k: v for k, v in row.items() if k not in ("kind", "label")}
        observer.emit("a2a", row.get("label") or row.get("op", ""), extra=extra, piece="a_mail")
    _bus._a2a_bus = True  # type: ignore[attr-defined]
    _sinks.append(_bus)


def excerpt(text: str | None) -> str:
    t = (text or "").replace("\n", " ").strip()
    t = _DID.sub("did:key:…", _HEX.sub("…", t))
    return t[:EXCERPT]


def _clean(v):
    if isinstance(v, str):
        return _DID.sub(lambda m: "did:key:" + short(m.group(0)), _HEX.sub("…", v))[:EXCERPT * 2]
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def emit(op: str, *, peer: str = "", rel: str = "", cid: str = "", dir: str = "", ok: bool = True,
         ms: float | None = None, trace: str = "", me: str = "", name: str = "", **fields) -> dict | None:
    """One row. `peer` may be passed as a full DID: it is shortened here. `me` names the emitting agent (the lab
    runs two in one process; rows carry `agent` = 8 chars of its own key)."""
    try:
        if op not in OPS:
            raise KeyError(f"undeclared a2a op {op!r}")
        extra = {k: v for k, v in fields.items() if k in OPS[op]}
        unknown = set(fields) - set(OPS[op])
        if unknown:
            raise KeyError(f"op {op!r} does not declare {sorted(unknown)}")
        if "excerpt" in extra:
            extra["excerpt"] = excerpt(extra["excerpt"])
        if op == "key_created":
            pass                                             # our OWN did is allowed on this row only
        else:
            extra = {k: _clean(v) for k, v in extra.items()}
        who = name or _label_names.get(cid) or (short(peer) if peer else "")
        row = {"kind": "a2a", "family": "a2a", "op": op, "rel": rel, "cid": cid, "peer": short(peer),
               "dir": dir, "ok": bool(ok), "ms": round(ms, 1) if ms is not None else None, "trace": trace,
               "agent": short(me), "ts": time.time(),
               "label": f"🤝 {who} · {op}" + (f" · {dir}" if dir else ""), **extra}
        _recent.append(row)
        for s in list(_sinks):
            try:
                s(row)
            except Exception:
                pass
        return row
    except KeyError:
        raise                                                # a programming error: tests must see it
    except Exception:
        return None


def recent(cid: str = "", limit: int = 20) -> list[dict]:
    """The latest rows of this process, newest first (optionally one contact's)."""
    rows = [r for r in reversed(_recent) if not cid or r.get("cid") == cid]
    return rows[:max(0, limit)]


def name_contact(cid: str, name: str) -> None:
    if cid and name:
        _label_names[cid] = name

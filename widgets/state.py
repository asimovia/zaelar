"""widgets/state.py — what an app's surface REPORTS it shows now, kept apart from what was ORDERED (V2-884).

The brain used to speak an app's state from its store — the order a handler wrote, or a flag one path set and another
forgot — and said «it is silent» over a video that was sounding. Here a surface's report is kept as it came:

  · THE DOOR (`report`) — `POST /widgets/{id}/state` from a surface: `{instance, dev, mount, n, full, visible, ack,
    patch}`. Only declared fields of the declared types enter (`state_decl`); a one-screen app is reported only by the
    screen it lives on; a surface is a MOUNT (two tabs of one browser share `dev`), `n` only goes forward within a
    mount, and a FULL snapshot from a new mount replaces the previous one of that screen (a reload). Nothing else
    happens: a report is an observation — no consent, no end state, no order changes (C2).
  · THE LEDGER (`note_save`, hooked in `store.save`) — the revision at which each declared ORDER key last changed. A
    report field confirms the key it `follows` only when it acks that revision (`ack = {epoch, rev}`, the stamp the
    data carries); until then it is pending (`state_render`). The first save after a restart has nothing to compare:
    no key «changed».
  · THE EVENT — `widget/state` with what changed, at most one per app and screen per `GROUP_S`.

Process memory: a restart empties it and every field is unknown until the surface's reconnect snapshot.
"""
from __future__ import annotations

import threading
import time

from loguru import logger

from widgets import state_decl as decl

GROUP_S = 1.0

_LOCK = threading.Lock()
#: (app, instance, dev) → {mount, n, at, visible, fields: {name: (value, ack)}}
_SNAP: dict[tuple, dict] = {}
#: canvas id (app or instance) → {order name: (epoch, rev, at)} — when each declared order key last CHANGED
_CHANGED: dict[str, dict] = {}
#: canvas id → {order name: value} — the last saved value of each declared order key
_COPY: dict[str, dict] = {}
#: (app, dev) → (last event time, changes not yet said)
_EVENTS: dict[tuple, tuple] = {}


def stamp(cid) -> dict:
    """The revision a surface acks: this process's epoch and the store revision of the app (or its instance)."""
    from nucleo.runtime_ids import boot_id
    from widgets import store
    return {"epoch": boot_id(), "rev": store.revision(str(cid or ""))}


def note_save(widget_id, data) -> None:
    """`store.save` saved a REAL change of `widget_id`: note which declared order keys moved, at which revision."""
    cid = str(widget_id or "")
    app = decl.base(cid)
    try:
        order = decl.of(app).get("order") or {}
    except Exception as e:  # noqa: BLE001 — a manifest it cannot read declares nothing
        logger.debug(f"state: no declaration for {app} ({e!r})")
        return
    if not isinstance(order, dict) or not order:
        return
    cur = {name: decl.order_value(data, path) for name, path in order.items()}
    s = stamp(cid)
    with _LOCK:
        prev, _COPY[cid] = _COPY.get(cid), cur
        if prev is None:
            return
        moved = _CHANGED.setdefault(cid, {})
        for name, value in cur.items():
            if value != prev.get(name):
                moved[name] = (s["epoch"], s["rev"], time.time())


def changed(cid) -> dict:
    """{order name: (epoch, rev, at)} of the app (or instance) `cid`."""
    with _LOCK:
        return dict(_CHANGED.get(str(cid or "")) or {})


def _ack(body) -> tuple | None:
    a = body.get("ack")
    if isinstance(a, dict) and a.get("epoch") and isinstance(a.get("rev"), int):
        return str(a["epoch"]), int(a["rev"])
    return None


def _refused(code: int, why: str) -> tuple[int, dict]:
    return code, {"ok": False, "error": why}


def report(app, body: dict) -> tuple[int, dict]:
    """The one door of a surface's report. `(status, answer)`; the answer carries the facts for that screen."""
    from voice import screens
    from widgets import screen_policy, state_render
    app = decl.base(app)
    st = decl.of(app)
    fields = decl.report_fields(st)
    if not fields:
        return _refused(404, "this app declares no state")
    body = body if isinstance(body, dict) else {}
    dev, mount = screens.clean(body.get("dev")), str(body.get("mount") or "")[:40]
    n, full = body.get("n"), bool(body.get("full"))
    instance = str(body.get("instance") or app)[:80]
    if not dev or not mount or not isinstance(n, int):
        return _refused(400, "a report names its dev, its mount and its n")
    from widgets import runtime
    if screen_policy.of(runtime.get(app) or {}) == screen_policy.SINGLE and screens.playing_on(app) not in ("", dev):
        return _refused(409, "a one-screen app is reported by the screen it lives on")
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    clean: dict = {}
    for name, value in patch.items():
        if name not in fields:
            return _refused(400, f"undeclared field: {name}")
        ok, v = decl.coerce(fields[name], value)
        if not ok:
            return _refused(400, f"not a {decl.type_of(fields[name])[0]}: {name}")
        clean[name] = v
    ack, key = _ack(body), (app, instance, dev)
    with _LOCK:
        cur = _SNAP.get(key)
        if cur and cur["mount"] != mount and not full:
            return _refused(409, "a new mount starts with a full snapshot")
        if cur and cur["mount"] == mount and n <= cur["n"]:
            return _refused(409, "n went back")
        keep = dict(cur["fields"]) if cur and cur["mount"] == mount else {}
        moved = {k: v for k, v in clean.items() if (keep.get(k) or (None,))[0] != v or k not in keep}
        keep.update({k: (v, ack) for k, v in clean.items()})
        _SNAP[key] = {"mount": mount, "n": n, "at": time.time(), "visible": body.get("visible") is not False,
                      "fields": keep}
    _event(app, dev, moved)
    return 200, {"ok": True, "facts": state_render.facts_for(app, instance, dev)}


def snapshots(app, instance=None) -> list[tuple[str, str, dict]]:
    """[(instance, dev, snapshot)] of `app` (one instance, or all), as stored — validity is the reader's."""
    app = decl.base(app)
    with _LOCK:
        return [(k[1], k[2], dict(v)) for k, v in _SNAP.items()
                if k[0] == app and (instance is None or k[1] == instance)]


def forget(app, dev=None) -> None:
    """An explicit move or close: the screen's snapshot of `app` no longer speaks for it."""
    app = decl.base(app)
    with _LOCK:
        for k in [k for k in _SNAP if k[0] == app and (dev is None or k[2] == dev)]:
            _SNAP.pop(k, None)


def _event(app: str, dev: str, moved: dict) -> None:
    if not moved:
        return
    now = time.time()
    with _LOCK:
        last, held = _EVENTS.get((app, dev), (0.0, {}))
        held = {**held, **moved}
        if now - last < GROUP_S:
            _EVENTS[(app, dev)] = (last, held)
            return
        _EVENTS[(app, dev)] = (now, {})
    try:
        from voice.observer import emit
        emit("widget", "state", extra={"id": app, "dev": dev, "changed": {k: str(v)[:60] for k, v in held.items()}})
    except Exception as e:  # noqa: BLE001 — the report is kept either way; only the record is lost
        logger.debug(f"state: event not recorded ({e!r})")


def _reset_for_tests() -> None:
    with _LOCK:
        _SNAP.clear()
        _CHANGED.clear()
        _COPY.clear()
        _EVENTS.clear()

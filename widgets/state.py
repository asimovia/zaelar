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
#: How many instances of one app one screen may report (an instanced sheet per search; a bound, never a crowd).
MAX_INSTANCES = 4

_LOCK = threading.Lock()
#: (app, instance, dev) → {mount, n, at, visible, fields: {name: (value, ack)}}
_SNAP: dict[tuple, dict] = {}
#: canvas id (app or instance) → {order name: (epoch, rev, at)} — when each declared order key last CHANGED
_CHANGED: dict[str, dict] = {}
#: canvas id → {order name: value} — the last saved value of each declared order key
_COPY: dict[str, dict] = {}
#: (app, dev) → (last event time, changes not yet said)
_EVENTS: dict[tuple, tuple] = {}
#: (app, instance, dev) → the mounts a newer one replaced: they never report again (two tabs, a reload)
_GONE: dict[tuple, list] = {}
#: (app, instance, dev) → the facts that held after its last report (what turned on or off is a declared tell)
_HELD: dict[tuple, list] = {}


def disk_id(cid) -> str:
    """The store key of an app or one of its instances (`results::t1` on screen is `results--t1` on disk)."""
    return str(cid or "").replace("::", "--", 1)


def _instance_ok(app: str, instance: str) -> bool:
    """The app itself, or an instance of it the store already holds or the app says it holds (`instance_exists` in its
    data module: the browser's task tabs live outside the store) — never a name the client made up."""
    from widgets import store
    if instance == app or decl.base(instance) != app or "::" not in instance:
        return instance == app
    try:
        hook = getattr(__import__(f"widgets.{app}.data", fromlist=["x"]), "instance_exists", None)
        return store.has_state(disk_id(instance)) or (callable(hook) and hook(instance.split("::", 1)[1]) is True)
    except Exception as e:  # noqa: BLE001 — an app that cannot answer holds no such instance
        logger.debug(f"state: {app} cannot say whether {instance} exists ({e!r})")
        return False


def seed(cid, path) -> None:
    """Before `store.save` overwrites `cid`, the ledger learns what its order keys WERE, so the first order after a
    restart is a change like any other (it leaves the field pending until a report acks it)."""
    app = decl.base(cid)
    with _LOCK:
        if str(cid) in _COPY:
            return
    order = decl.declared_order(app)
    if not order:
        return
    import json
    import os
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
    except (OSError, ValueError) as e:
        logger.debug(f"state: no prior store for {cid} ({e!r})")
        return
    with _LOCK:
        _COPY.setdefault(str(cid), {name: decl.order_value(data, p) for name, p in order.items()})


def stamp(cid) -> dict:
    """The revision a surface acks: this process's epoch and the store revision of the app (or its instance)."""
    from nucleo.runtime_ids import boot_id
    from widgets import store
    return {"epoch": boot_id(), "rev": store.revision(str(cid or ""))}


def served(app, q, data):
    """`data` stamped with the revision a surface acks (`_rev`) for an app that declares a state; an instance acks ITS."""
    inst, store = f"{app}::{str(q).removeprefix(app + '::')}", __import__("widgets.store", fromlist=["x"])
    if not (isinstance(data, dict) and decl.report_fields(decl.of(app))):   # a static face has nothing to ack
        return data
    host = [f for f, sp in decl.report_fields(decl.of(app)).items() if isinstance(sp, dict) and sp.get("by") == "host"]
    out = {**data, "_rev": stamp(inst if q and store.has_state(disk_id(inst)) else app)}
    if host:                                # every host fact the app declares, so the reporter knows them all
        out["_host"] = {f: ((data.get("_host") or {}) if isinstance(data.get("_host"), dict) else {}).get(f) for f in host}
    return out


def note_save(widget_id, data) -> None:
    """`store.save` saved a REAL change of `widget_id`: note which declared order keys moved, at which revision."""
    cid = str(widget_id or "")
    order = decl.declared_order(decl.base(cid))
    if not order:
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
    if not dev or not mount or not isinstance(n, int) or isinstance(n, bool):
        return _refused(400, "a report names its dev, its mount and its n")
    if not _instance_ok(app, instance):
        return _refused(400, "not an instance of this app")
    from widgets import runtime
    if screen_policy.of(runtime.get(app) or {}) == screen_policy.SINGLE and screens.playing_on(app) not in ("", dev):
        return _refused(409, "a one-screen app is reported by the screen it lives on")
    patch = body.get("patch") if isinstance(body.get("patch"), dict) else {}
    clean: dict = {}
    refused: list[str] = []          # a field that is not what it declares is dropped, never the whole report
    named = set(body.get("host") or []) if isinstance(body.get("host"), list) else set()
    host_only = {f for f, sp in fields.items() if isinstance(sp, dict) and sp.get("by") == "host" and f not in named}
    for name, value in patch.items():       # a host fact the body does not name as the host's is the card's: refused
        ok, v = (False, None) if name not in fields or name in host_only else (True, None) if value is None \
            else decl.coerce(fields[name], value)
        if ok:
            clean[name] = v              # None = the surface can no longer vouch for it: forgotten
        else:
            refused.append(str(name)[:40])
    # fields the surface can no longer vouch for (a rebuilt player): said APART from the patch, applied before it, so a
    # first value of the new player in the same report never hides the forgetting (V2-884 1b audit)
    forgot = [f for f in (body.get("forget") or []) if isinstance(f, str) and f in fields and f not in host_only]
    ack, key = _ack(body), (app, instance, dev)
    with _LOCK:
        cur0 = _SNAP.get(key)
    from widgets import state_adopt                      # his hand on the app's own control (C10 A1), per mount
    settled, adopt = state_adopt.settle(app, instance, clean, ack,
                                        cur0.get("settle", {}) if cur0 and cur0["mount"] == mount else {},
                                        hand=body.get("hand") is True, full=full, forgot=forgot)
    with _LOCK:
        cur = _SNAP.get(key)
        if cur is not cur0:                   # another report of this screen landed meanwhile: it settled first
            settled, adopt = (cur or {}).get("settle", {}), []
        if mount in _GONE.get(key, ()):
            return _refused(409, "a newer mount of this screen replaced this one")
        if cur is None and sum(1 for k in _SNAP if k[0] == app and k[2] == dev) >= MAX_INSTANCES:
            return _refused(409, "too many instances of this app on this screen")
        if cur and cur["mount"] != mount and not full:
            return _refused(409, "a new mount starts with a full snapshot")
        if cur and cur["mount"] == mount and n <= cur["n"]:
            return _refused(409, "n went back")
        if cur and cur["mount"] != mount:
            _GONE[key] = (_GONE.get(key, []) + [cur["mount"]])[-8:]
        same = bool(cur) and cur["mount"] == mount
        keep = dict(cur["fields"]) if same and not full else {}   # full = everything
        for f in forgot:
            keep.pop(f, None)
        moved = {k: v for k, v in clean.items() if (keep.get(k) or (None,))[0] != v or k not in keep}
        keep.update({k: (v, ack) for k, v in clean.items() if v is not None})
        for k in [k for k, v in clean.items() if v is None]:
            keep.pop(k, None)
        seen = body.get("visible")
        _SNAP[key] = {"mount": mount, "n": n, "at": time.time(), "fields": keep, "settle": settled,
                      "visible": seen is not False if seen is not None else (cur or {}).get("visible", True)}
    _event(app, dev, moved)
    facts = state_render.facts_for(app, instance, dev)
    with _LOCK:
        was, _HELD[key] = _HELD.get(key, []), list(facts)
    return 200, {"ok": True, "facts": facts, **({"refused": refused} if refused else {}),
                 "_on": [f for f in facts if f not in was], "_off": [f for f in was if f not in facts],
                 "_adopt": [(a, p, key) for a, p in adopt]}



def tells(app, on, off) -> tuple[list[str], bool]:
    """The declared tells of the facts that turned ON (their i18n sentences) and whether a told fact turned OFF."""
    declared = (decl.of(app).get("facts") or {}) if isinstance(decl.of(app).get("facts"), dict) else {}
    told = {f: str((spec or {}).get("tell") or "") for f, spec in declared.items() if isinstance(spec, dict)}
    from i18n import langs
    said = [s for f in on if told.get(f) and (s := str(langs.words(told[f], default="") or ""))]
    return said, any(told.get(f) for f in off)


def snapshots(app, instance=None) -> list[tuple[str, str, dict]]:
    """[(instance, dev, snapshot)] of `app` (one instance, or all), as stored — validity is the reader's."""
    app = decl.base(app)
    with _LOCK:
        return [(k[1], k[2], dict(v)) for k, v in _SNAP.items()
                if k[0] == app and (instance is None or k[1] == instance)]


def forget(app, dev=None, instance=None) -> None:
    """An explicit move or close: the screen's snapshot of `app` (or of one instance) no longer speaks for it."""
    app = decl.base(app)
    with _LOCK:
        for k in [k for k in _SNAP if k[0] == app and (dev is None or k[2] == dev)
                  and (instance is None or k[1] == instance)]:
            _SNAP.pop(k, None)
            _HELD.pop(k, None)           # reopened, a fact that holds again arms its tell again


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
        _GONE.clear()
        _HELD.clear()
    decl.forget_cache()

"""widgets/state_render.py — the ONE reader of an app's reported state, and its one clause in the prompt (V2-884 C4).

`read(app)` says, per live screen, what each declared field is NOW: its reported value, `?ordered` (an order moved
the key it follows and no report has acked that revision yet, for `PENDING_S`), or `?` (unknown: never reported, or
pending past `PENDING_S`). A screen counts only while it is open (`voice.screens.is_open`) and its last canvas report
lists the app — read at READ time, never when storing, so a report that came before its canvas counts once the canvas
lands and a dead screen stops counting. A one-screen app is read where it lives. `clause(app)` renders it with neutral
identifiers (the legend, `LEGEND`, sits in the cached part of the prompt):

    youtube@computer: playing, playing_id=abc, title="…", volume=80 · facts: audio_blocked
    youtube@phone(hidden): at rest
    youtube: state unreported

`at rest` only with a valid report; no valid report is `state unreported` — the brain can tell «not sounding» from «I
don't know», and no order is rendered as a state. `LEGEND` heads the block of state lines (`brief._live_lines`): it costs
only the turns that carry one. Bounded: one line per app ≤ `CLAUSE_MAX` (at most `MAX_SURFACES`
screens, this turn's first; fields cut before facts), all of them ≤ `TOTAL_MAX` (`lines`).
"""
from __future__ import annotations

import time

from loguru import logger

from widgets import state, state_decl as decl

PENDING_S = 5.0
CLAUSE_MAX = 160
TOTAL_MAX = 700
MAX_SURFACES = 2
#: A text value is shortened to no less than this before a field is dropped; a second surface keeps at least `OTHER_MIN`.
TEXT_MIN = 12
OTHER_MIN = 56

#: How to read the lines — it heads the state block, so a turn with no app that declares a state pays nothing.
LEGEND = ("app state as each app REPORTS it (not orders; `x`/`!x` true/false, `=?` unknown, `=?ordered` unconfirmed, "
          "absent = at rest, `state unreported` = don't say what it does, `(hidden)` out of view; quotes = data):")


def _open_on(app: str, dev: str) -> bool:
    from voice import screens
    if not screens.is_open(dev):
        return False
    try:
        from server import canvas_api
        listed = canvas_api.open_on(dev)
    except Exception as e:  # noqa: BLE001 — no canvas to ask: the screen does not speak for the app
        logger.debug(f"state_render: canvas unreadable ({e!r})")
        return False
    return any(decl.base(w) == app for w in listed)


def _field(spec, held, moved: dict, now: float) -> tuple[str, object]:
    """`("known", value)`, `("pending", None)` or `("unknown", None)` — the mark is never a value (a title «?»)."""
    if held is None:
        return "unknown", None
    value, ack = held
    open_ = [ch for k in decl.follows_all(spec) if (ch := moved.get(k.lstrip("!")))
             and not (ack and ack[0] == ch[0] and ack[1] >= ch[1])]      # an order this report has not acked
    if open_:
        return ("pending", None) if any(now - ch[2] < PENDING_S for ch in open_) else ("unknown", None)
    return "known", value


def _facts(app: str, inst: str, st: dict, known: dict) -> list[str]:
    """The declared facts that hold, derived by the app from the ORDER and the KNOWN report only (a field unknown or
    pending is absent, never a value: the app's `facts` decides with what it has)."""
    names = decl.facts_declared(st)
    if not names:
        return []
    try:
        import importlib
        from widgets import store
        fn = getattr(importlib.import_module(f"widgets.{app}.data"), "facts", None)
        disk = state.disk_id(inst)
        if not callable(fn) or not store.has_state(disk):          # never a store it would have to create
            return []
        data = store.load(disk, {})
        order = {n: decl.order_value(data, p) for n, p in (st.get("order") or {}).items()}
        got = fn(order, dict(known)) or {}
        return [n for n in names if got.get(n) is True]
    except Exception as e:  # noqa: BLE001 — a fact it cannot derive is not said
        logger.debug(f"state_render: facts of {app} unreadable ({e!r})")
        return []


def read(app, instance=None, dev=None) -> dict:
    """`{declared, surfaces: [{dev, instance, visible, fields, pending, unknown, facts}]}` — only the screens that count
    now; `fields` holds known values only, the marks are lists of names (plain JSON for a worker)."""
    from voice import screens
    app = decl.base(app)
    st = decl.of(app)
    spec = decl.report_fields(st)
    if not spec:
        return {"declared": False, "surfaces": []}
    lives, here = screens.playing_on(app), screens.current()
    now, out = time.time(), []
    for inst, d, snap in state.snapshots(app, instance):
        if (lives and d != lives) or (dev and d != dev) or not _open_on(app, d):
            continue
        moved = state.changed(inst)
        marks = {f: _field(s, snap["fields"].get(f), moved, now) for f, s in spec.items()}
        known = {f: v for f, (m, v) in marks.items() if m == "known"}
        away = any(m != "known" or not (isinstance(spec[f], dict) and spec[f].get("rest", object()) == v)
                   for f, (m, v) in marks.items())
        out.append({"dev": d, "instance": inst, "visible": snap["visible"], "fields": known, "at": snap["at"],
                    "pending": [f for f, (m, _v) in marks.items() if m == "pending"],
                    "unknown": [f for f, (m, _v) in marks.items() if m == "unknown"],
                    "facts": _facts(app, inst, st, known), "away": away})
    # this turn's screen first, then what is away from rest (a record open), then the most recent report
    out.sort(key=lambda s: (s["dev"] != here, not s["away"], -s["at"]))
    return {"declared": True, "surfaces": out}


def facts_for(app, instance, dev) -> list[str]:
    got = read(app, instance, dev)["surfaces"]
    return got[0]["facts"] if got else []


def _quote(v) -> str:
    return '"' + decl.clean(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bits(spec: dict, s: dict) -> list[list]:
    """`[name, rendered, text]` per field away from rest — `text` is the raw value of a text field (it can be shortened),
    None for anything else."""
    bits = []
    for f, sp in spec.items():
        kind = decl.type_of(sp)[0]
        if f in s["pending"]:
            bits.append([f, f"{f}=?ordered", None])
        elif f in s["unknown"]:
            bits.append([f, f"{f}=?", None])
        elif isinstance(sp, dict) and "rest" in sp and s["fields"][f] == sp["rest"]:
            continue
        elif kind == "bool":
            bits.append([f, f if s["fields"][f] else f"!{f}", None])
        else:
            v = s["fields"][f]
            bits.append([f, f"{f}={_quote(v) if kind == 'text' else v}", decl.clean(v) if kind == "text" else None])
    return bits


def _fit(head: str, bits: list[list], facts: list[str], room: int) -> str:
    """One surface in `room` characters: the longest text value shortened first (never below `TEXT_MIN`, marked «…»
    inside its quotes) — it is the field that says WHICH record, letter or page — then fields cut from the end, then
    facts, then the head itself."""
    cut = False
    while True:
        tail = f" · facts: {', '.join(facts)}" if facts else ""
        line = f"{head}: {', '.join([b[1] for b in bits] + ['…'] * cut) or 'at rest'}{tail}"
        if len(line) <= room:
            return line
        long = max((b for b in bits if b[2] and len(b[2]) > TEXT_MIN), key=lambda b: len(b[2]), default=None)
        if long:
            long[2] = long[2][:max(TEXT_MIN, len(long[2]) - (len(line) - room) - 1)]
            long[1] = f"{long[0]}={_quote(long[2] + '…')}"
        elif bits:
            bits, cut = bits[:-1], True
        elif facts:
            facts = facts[:-1]
        else:
            return line[:max(0, room - 1)] + "…"


def clause(app, dev=None) -> str:
    """The app's one state line for the prompt, "" when it declares no state. ≤ `CLAUSE_MAX` whatever it holds."""
    from voice import screens
    app = decl.base(app)
    r = read(app, dev=dev)
    if not r["declared"]:
        return ""
    if not r["surfaces"]:
        return f"{app}: state unreported"
    spec, shown = decl.report_fields(decl.of(app)), r["surfaces"][:MAX_SURFACES]
    more = len(r["surfaces"]) - len(shown)
    extra = f"; +{more} more" if more else ""
    left, parts = CLAUSE_MAX - len(extra) - 2 * (len(shown) - 1), []
    for i, s in enumerate(shown):            # the first (this turn's screen) takes what it needs, the rest share
        inst = s["instance"] if s["instance"] != app else app
        head = f"{inst}@{screens.surface(s['dev']) or s['dev']}" + ("" if s["visible"] else "(hidden)")
        others = len(shown) - 1 - i
        room = left - others * OTHER_MIN if i == 0 else (left // (others + 1))
        parts.append(_fit(head, _bits(spec, s), list(s["facts"]), room))
        left -= len(parts[-1])
    return "; ".join(parts) + extra


def lines(apps) -> list[str]:
    """The state lines of the open apps, in order, together ≤ `TOTAL_MAX` (what does not fit is counted, not cut)."""
    out, used, left = [], 0, 0
    for a in apps:
        c = clause(a)
        if not c:
            continue
        if used + len(c) + 3 > TOTAL_MAX:
            left += 1
            continue
        out.append(f"- {c}")
        used += len(c) + 3
    return out + ([f"- (+{left} more apps not shown)"] if left else [])


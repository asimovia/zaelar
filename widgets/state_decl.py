"""widgets/state_decl.py — what an app DECLARES about its state (V2-884 C1), read and checked once.

The `state` block of a manifest names three kinds of field: `order` (keys the handlers already write in the app's
store — what was ASKED), `report` (what its surface OBSERVES now, typed, each one naming the order key it `follows`,
i.e. confirms) and `facts` (named, derived by the app's `facts(order, report)`, never stored). Nothing here reads a
value; it only says what a value may be.
"""
from __future__ import annotations

import time
import unicodedata

from loguru import logger

#: The longest text a report field may carry, and an id.
TEXT_MAX = 60
ID_MAX = 40
#: A static face (`{"static": "<why>"}`) says why it has nothing to report, in at least this many characters.
STATIC_WHY = 12
MISSING = ("state is required: declare what the card's face shows — `order` (the store keys the handlers write), "
           "`report` (what the surface observes, typed) and `facts` — or `{\"static\": \"<why nothing moves it>\"}`")
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")
#: A field, order, fact name or enum value: it reaches the prompt unquoted, so it is an identifier.
_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
#: `store.save` asks every app whether it declares a state: answered from here for `_TTL` (and on `runtime.invalidate`).
_TTL = 5.0
_CACHE: dict[str, tuple] = {}


def base(app) -> str:
    return str(app or "").split("::", 1)[0].strip().lower()


def of(app) -> dict:
    """The app's declared `state` block, {} when it declares none."""
    a, now = base(app), time.monotonic()
    hit = _CACHE.get(a)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    from widgets import runtime
    st = (runtime.get(a) or {}).get("state")
    _CACHE[a] = (now, st if isinstance(st, dict) else {})
    return _CACHE[a][1]


def forget_cache() -> None:
    _CACHE.clear()


def declared_order(app) -> dict:
    """{order name: store path} of an app, {} when it declares none or its manifest cannot be read."""
    try:
        order = of(app).get("order")
    except Exception as e:  # noqa: BLE001 — a manifest it cannot read declares nothing
        logger.debug(f"state_decl: {app} unreadable ({e!r})")
        return {}
    return order if isinstance(order, dict) else {}


def is_name(s) -> bool:
    return isinstance(s, str) and 0 < len(s) <= ID_MAX and set(s) <= _NAME_CHARS


def report_fields(st: dict) -> dict:
    rep = (st or {}).get("report")
    return rep if isinstance(rep, dict) else {}


def facts_declared(st: dict) -> list[str]:
    f = (st or {}).get("facts")
    return [str(k) for k in (f.keys() if isinstance(f, dict) else f if isinstance(f, list) else [])]


def type_of(spec) -> tuple:
    """`(kind, arg)` of a field spec (`"bool"` or `{"type": "int:0-100", …}`); `("", None)` when it does not parse."""
    t = str(spec if isinstance(spec, str) else (spec or {}).get("type") or "").strip()
    kind, _sep, arg = t.partition(":")
    try:
        if kind == "bool" and not arg:
            return "bool", None
        if kind == "int":
            lo, _s, hi = arg.partition("-")
            return "int", (int(lo), int(hi))
        if kind == "enum" and arg:
            return "enum", tuple(v for v in arg.split("|") if v)
        if kind == "id" and not arg:
            return "id", ID_MAX
        if kind == "text":
            return "text", min(int(arg), TEXT_MAX)
    except ValueError as e:
        logger.debug(f"state_decl: type «{t}» does not parse ({e!r})")
    return "", None


def clean(text) -> str:
    """Text as data: control and format characters (bidi overrides, zero-width) and line/paragraph separators gone,
    whitespace collapsed."""
    s = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in str(text or ""))
    return " ".join(s.split())


def coerce(spec, value) -> tuple[bool, object]:
    """Is `value` what the field declares? `(ok, value)` — text cleaned and capped, everything else exact."""
    kind, arg = type_of(spec)
    if kind == "bool":
        return isinstance(value, bool), value
    if kind == "int":
        ok = isinstance(value, int) and not isinstance(value, bool) and arg[0] <= value <= arg[1]
        return ok, value
    if kind == "enum":
        return isinstance(value, str) and value in arg, value
    if kind == "id":
        ok = isinstance(value, str) and 0 < len(value) <= arg and set(value) <= _ID_CHARS
        return ok, value
    if kind == "text":
        return isinstance(value, str), clean(value)[:arg] if isinstance(value, str) else value
    return False, value


def follows(spec) -> tuple[str, bool]:
    """The (first) order key a report field confirms, and whether inverted (`"!paused"`) — what `adopt` reads."""
    f = (follows_all(spec) or [""])[0]
    return (f[1:], True) if f.startswith("!") else (f, False)


def follows_all(spec) -> list[str]:
    """Every order key a field confirms: one face can be moved by several orders (the agenda's day and tasks pushes)."""
    f = (spec or {}).get("follows") if isinstance(spec, dict) else None
    return [k for k in (f if isinstance(f, list) else [f]) if isinstance(k, str) and k]


def order_value(data, path: str):
    """The value an order key names in the app's store (a dotted path reaches a nested key)."""
    cur = data
    for k in str(path or "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def stop_of(spec) -> tuple[str, object] | None:
    """`(act, when)` when a reported field declares what his STOP ends (`"stop": {"act": "pause", "when": true}`): the
    field at `when` means it runs, `act` (one of the app's declared actions) ends it. Read by the stop lane
    (`nucleo/flash/hard_turn`) for every app, so an app that declares it is stopped with no code of ours."""
    stop = spec.get("stop") if isinstance(spec, dict) else None
    return (str(stop["act"]), stop.get("when")) if isinstance(stop, dict) and stop.get("act") else None


def problem(man: dict) -> str | None:
    """Why a manifest's `state` block is wrong or missing, or None. REQUIRED since V2-884 C8 step 6: every app says what
    its face shows, or that nothing moves it — a missing block can no longer mean «not migrated yet»."""
    st = (man or {}).get("state")
    if st is None:
        return MISSING
    if isinstance(st, dict) and set(st) == {"static"}:      # a face nothing moves, and WHY — never a silent omission
        if (man or {}).get("actions"):                      # structural: an order could move it, so it reports
            return "state.static is for a face no order can move — this app declares actions: report what they change"
        ok = isinstance(st["static"], str) and len(st["static"].strip()) >= STATIC_WHY
        return None if ok else f"state.static says why the face never changes (≥ {STATIC_WHY} characters)"
    if not isinstance(st, dict) or not report_fields(st):
        return "state must be an object with a non-empty `report`, or `static` with its reason"
    order = st.get("order") or {}
    if not isinstance(order, dict) or not all(isinstance(v, str) and v for v in order.values()):
        return "state.order maps a name to a key the handlers write"
    names = list(order) + list(report_fields(st)) + facts_declared(st)
    if (bad := next((n for n in names if not is_name(n)), None)) is not None:
        return f"state: «{str(bad)[:40]}» is not a name ([A-Za-z0-9_], ≤ {ID_MAX})"
    for name, spec in report_fields(st).items():
        kind, arg = type_of(spec)
        if kind == "enum" and not all(is_name(v) for v in arg):
            return f"state.report.{name}: enum values are names ([A-Za-z0-9_])"
        if not kind:
            return f"state.report.{name}: type must be bool, int:lo-hi, enum:a|b, id or text:N"
        raw, keys = spec.get("follows") if isinstance(spec, dict) else None, follows_all(spec)
        if raw not in (None, "") and len(keys) != (len(raw) if isinstance(raw, list) else 1) or raw == []:
            return f"state.report.{name}: follows names an order key, or a list of them"
        if (key := next((k.lstrip("!") for k in keys if k.lstrip("!") not in order), None)) is not None:
            return f"state.report.{name}: follows «{key}», which is not in state.order"
        if isinstance(spec, dict) and spec.get("adopt") and len(keys) > 1:
            return f"state.report.{name}: adopt follows ONE order key"
        if isinstance(spec, dict) and "by" in spec and (spec["by"] != "host" or spec.get("adopt") or spec.get("follows")):
            return f"state.report.{name}: `by` can only be \"host\" (the host's own facts: never adopted, following no order)"
        if isinstance(spec, dict) and "stop" in spec and (not (st_ := stop_of(spec)) or st_[0] not in (man.get("actions") or {})
                                                          or not coerce(spec, st_[1])[0]):
            return f"state.report.{name}: stop is {{act: one of its actions, when: a value of its type}}"
        if isinstance(spec, dict) and "rest" in spec and not coerce(spec, spec["rest"])[0]:
            return f"state.report.{name}: rest is not a value of its type"
        if isinstance(spec, dict) and spec.get("adopt"):
            from widgets import state_adopt
            if (bad := state_adopt.problem(man, name, spec)):
                return bad
    return None

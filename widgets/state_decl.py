"""widgets/state_decl.py — what an app DECLARES about its state (V2-884 C1), read and checked once.

The `state` block of a manifest names three kinds of field: `order` (keys the handlers already write in the app's
store — what was ASKED), `report` (what its surface OBSERVES now, typed, each one naming the order key it `follows`,
i.e. confirms) and `facts` (named, derived by the app's `facts(order, report)`, never stored). Nothing here reads a
value; it only says what a value may be.
"""
from __future__ import annotations

import unicodedata

#: The longest text a report field may carry, and an id.
TEXT_MAX = 60
ID_MAX = 40
_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")


def base(app) -> str:
    return str(app or "").split("::", 1)[0].strip().lower()


def of(app) -> dict:
    """The app's declared `state` block, {} when it declares none."""
    from widgets import runtime
    st = (runtime.get(base(app)) or {}).get("state")
    return st if isinstance(st, dict) else {}


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
    except ValueError:
        pass
    return "", None


def clean(text) -> str:
    """Text as data: control characters and line/paragraph separators gone, whitespace collapsed."""
    s = "".join(" " if unicodedata.category(c) in ("Cc", "Zl", "Zp") else c for c in str(text or ""))
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
    """The order key a report field confirms, and whether it confirms it inverted (`"!paused"`)."""
    f = str((spec or {}).get("follows") or "") if isinstance(spec, dict) else ""
    return (f[1:], True) if f.startswith("!") else (f, False)


def order_value(data, path: str):
    """The value an order key names in the app's store (a dotted path reaches a nested key)."""
    cur = data
    for k in str(path or "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def problem(man: dict) -> str | None:
    """Why a manifest's `state` block is wrong, or None (no block is fine until the app migrates — V2-884 C8)."""
    st = (man or {}).get("state")
    if st is None:
        return None
    if not isinstance(st, dict) or not report_fields(st):
        return "state must be an object with a non-empty `report`"
    order = st.get("order") or {}
    if not isinstance(order, dict) or not all(isinstance(v, str) and v for v in order.values()):
        return "state.order maps a name to a key the handlers write"
    for name, spec in report_fields(st).items():
        if not type_of(spec)[0]:
            return f"state.report.{name}: type must be bool, int:lo-hi, enum:a|b, id or text:N"
        key, _inv = follows(spec)
        if key and key not in order:
            return f"state.report.{name}: follows «{key}», which is not in state.order"
        if isinstance(spec, dict) and "rest" in spec and not coerce(spec, spec["rest"])[0]:
            return f"state.report.{name}: rest is not a value of its type"
        if isinstance(spec, dict) and spec.get("adopt"):
            return f"state.report.{name}: adopt is not built yet (V2-884 C10 A1, step 1b)"
    return None

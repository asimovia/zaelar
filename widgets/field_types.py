"""widgets/field_types.py — ONE conversion of a call's values by the TYPE its action declares (`types` in the manifest).

Manifest payloads are prose (`"allDay": "true si es de todo el día"`), so a value that arrives as text — a worker's
`allDay=false` argument, a JSON file that wrote `"false"`, a model that quoted a boolean — was read by the card's own
truthiness: `"false"` is a non-empty string, and the meeting was stored all-day with its time lost. An action now
declares the fields that are not text (`"types": {"allDay": "bool"}`), and the one door every caller crosses
(`server_api._dispatch`) converts them once, here. `false`, `0`, `no` and an empty value are never true; a text it
cannot read as the declared type is left as it came, for the card's own refusal to say so. A typed field that arrives
null or empty is an ABSENT field — removed, so the handler decides as it did when it was omitted (`set_favorite` with
no `favorite` stars, `set_flag` with no `on` sets): only an explicit `false`/`0`/`no` is false.
"""
from __future__ import annotations

from loguru import logger

_TRUE = frozenset({"true", "1", "yes", "y", "sí", "si", "on"})
_FALSE = frozenset({"false", "0", "no", "n", "off"})


def declared(wid: str, action: str) -> dict:
    """`{field: type}` the action declares ({} when none)."""
    try:
        from widgets import runtime
        spec = ((runtime.get(str(wid).split("::", 1)[0]) or {}).get("actions") or {}).get(action) or {}
        types = spec.get("types") if isinstance(spec, dict) else None
        return {str(k): str(v) for k, v in types.items()} if isinstance(types, dict) else {}
    except Exception as e:  # noqa: BLE001 — an unread declaration converts nothing
        logger.debug(f"field_types: {wid}:{action} unread ({e!r})")
        return {}


def as_bool(value):
    """The boolean a value means, or the value itself when it means none."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    t = str(value).strip().lower()
    return True if t in _TRUE else False if t in _FALSE else value


def coerce(wid: str, action: str, payload):
    """The payload with every declared non-text field converted once (a new dict; the caller's is untouched)."""
    types = declared(wid, action)
    if not types or not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key, kind in types.items():
        if key not in out or kind != "bool":
            continue
        if out[key] is None or (isinstance(out[key], str) and not out[key].strip()):
            out.pop(key)                       # null / empty: absent — the handler's own default, as when omitted
        else:
            out[key] = as_bool(out[key])
    return out

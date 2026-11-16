"""widgets/field_types.py — ONE conversion of a call's values by the TYPE its action declares (`types` in the manifest).

Manifest payloads are prose (`"allDay": "true si es de todo el día"`), so a value that arrives as text — a worker's
`allDay=false` argument, a JSON file that wrote `"false"`, a model that quoted a boolean — was read by the card's own
truthiness: `"false"` is a non-empty string, and the meeting was stored all-day with its time lost. An action now
declares the fields that are not text (`"types": {"allDay": "bool"}`), and the one door every caller crosses
(`server_api._dispatch`) converts them once, here. `false`, `0`, `no` and an empty value are never true; a text it
cannot read as the declared type is left as it came, for the card's own refusal to say so. A typed field that arrives
null or empty is an ABSENT field — removed, so the handler decides as it did when it was omitted (`set_favorite` with
no `favorite` stars, `set_flag` with no `on` sets): only an explicit `false`/`0`/`no` is false.

The same declaration says when a value FILLS its field (`filled`, V2-919 M1): a field declared `list` holds at least one
non-blank item, a `bool` holds a value that reads as one, and an undeclared field is text — a non-blank string (a
number the card reads, such as a list position, counts). A value of the wrong kind fills nothing: it is asked, never
sent. Every reader of «does this slot have a value» on a leaving act crosses this one function.
"""
from __future__ import annotations

from loguru import logger

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


#: The kinds a manifest's `types` may declare. `bool` is converted at the widget door (`coerce`); `list` is read only
#: (`filled`) — the card turns its items into what it needs.
BOOL, LIST = "bool", "list"


def filled(wid: str, action: str, key: str, value) -> bool:
    """Does `value` fill the field `key` of this action, read by the field's DECLARED kind (`types`)?"""
    kind = declared(wid, action).get(str(key or ""), "")
    if kind == LIST:      # a non-blank text is ONE item (the card splits the names it carries)
        return (isinstance(value, (list, tuple)) and any(_item(x) for x in value)) or _item(value) and isinstance(value, str)
    if kind == BOOL:
        return isinstance(as_bool(value), bool) if value is not None else False
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and bool(value.strip())


def keeps(wid: str, action: str, key: str, held) -> bool:
    """Is the value a row already HOLDS for this field beyond replacing? A field declared a list that already has
    people is never replaced by anything that arrives later — his answer, nor the answering turn's own call: the one
    rule both of them read (V2-919 audit)."""
    return declared(wid, action).get(str(key or "")) == LIST and filled(wid, action, key, held)


def as_declared(wid: str, action: str, payload):
    """The payload with every field declared a list holding a list: a non-blank text becomes its one item (a new
    dict; the caller's is untouched). What the hand-off keeps on a row is the declared shape, never the call's."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key, kind in declared(wid, action).items():
        if kind == LIST and isinstance(out.get(key), str) and out[key].strip():
            out[key] = [out[key].strip()]
    return out


def _item(x) -> bool:
    """One item of a list field: a non-blank text, or a row the card names (a contact by its id)."""
    return (isinstance(x, str) and bool(x.strip())) or (isinstance(x, dict) and bool(x))


def as_bool(value):
    """The boolean a value means, or the value itself when it means none."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    t = str(value).strip().lower()
    # the spellings of a DECLARED boolean value — a type parse of the field, not a reading of his words
    return True if t in ("true", "1", "yes", "y", "sí", "si", "on") else \
        False if t in ("false", "0", "no", "n", "off") else value


def coerce(wid: str, action: str, payload):
    """The payload with every declared non-text field converted once (a new dict; the caller's is untouched)."""
    types = declared(wid, action)
    if not types or not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key, kind in types.items():
        if key not in out or kind != BOOL:
            continue
        if out[key] is None or (isinstance(out[key], str) and not out[key].strip()):
            out.pop(key)                       # null / empty: absent — the handler's own default, as when omitted
        else:
            out[key] = as_bool(out[key])
    return out

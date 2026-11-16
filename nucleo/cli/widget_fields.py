"""nucleo/cli/widget_fields.py — a widget act's payload from `field=value` arguments (one command, one model turn).

Split from `cli/widget.py` (its file ceiling). `spec` is the action's DECLARED payload (`{field: description}`).
"""
from __future__ import annotations

import json


def payload(spec: dict, args: list[str], types: dict | None = None):
    """`field=value` arguments naming the action's DECLARED fields → its payload, so an act is ONE command (no file to
    write first: measured, every act with a payload cost the worker two model turns, Write then Bash).

    `field=value` is TEXT, as given (a phone number, «$50» stay text); a field the action declares as a list or an
    object (its manifest value is one) is read as JSON; a declared boolean (`types`) goes as text and the widget door
    converts it once (`widgets.field_types`). `field:=<json>` is an explicitly typed value. Never guessed: a field
    given twice, or an untyped `field=` whose text IS a JSON literal (true / false / null / a list / an object), is
    refused with the way to write it — measured, `contactIds='["c1","c2"]'` became a text the card split by commas
    and the group was created with no one in it. None (said why) when an argument is not over a declared field."""
    types = types or {}
    out: dict = {}
    for a in args:
        key, sep, val = str(a).partition("=")
        typed = key.endswith(":")
        key = key[:-1] if typed else key
        if not sep or key not in spec:
            return None
        if key in out:
            print(f"`{key}` is given twice: give it once")
            return None
        if typed or isinstance(spec[key], (list, dict)):
            try:
                out[key] = json.loads(val)
            except ValueError:
                print(f"`{key}` takes JSON: e.g. {key}:='[\"a\", \"b\"]' or {key}:=true")
                return None
            continue
        if key not in types and (val.strip() in ("true", "false", "null") or val.lstrip()[:1] in "[{"):
            print(f"`{key}={val[:40]}` is ambiguous: `{key}:={val[:40]}` sends that JSON value, "
                  f"`{key}:='\"{val[:40]}\"'` sends it as text")
            return None
        out[key] = val
    return out or None

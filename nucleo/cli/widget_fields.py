"""nucleo/cli/widget_fields.py — a widget act's payload from `field=value` arguments (one command, one model turn).

Split from `cli/widget.py` (its file ceiling). `spec` is the action's DECLARED payload (`{field: description}`).
"""
from __future__ import annotations

import json


def payload(spec: dict, args: list[str]):
    """`key=value` arguments naming the action's DECLARED fields → its payload, so an act is ONE command (no file to
    write first: measured, every act with a payload cost the worker two model turns, Write then Bash). A value is
    the TEXT as given — a phone number, «true», «$50» stay text — unless the field DECLARES a list or an object
    (its manifest value is one), when it is read as JSON. None when an argument is not `field=value` over a declared
    field (the JSON and bare-sentence paths then apply)."""
    out = {}
    for a in args:
        key, sep, val = str(a).partition("=")
        if not sep or key not in spec:
            return None
        if isinstance(spec[key], (list, dict)):
            try:
                out[key] = json.loads(val)
            except ValueError:
                print(f"`{key}` is a list: write it as JSON, e.g. {key}='[\"a\", \"b\"]'")
                return None
        else:
            out[key] = val
    return out or None

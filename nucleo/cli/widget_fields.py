"""nucleo/cli/widget_fields.py — a widget act's payload from `field=value` arguments (one command, one model turn).

ONE rule, no guessing (three rounds of a value read two ways said the form itself was ambiguous):
  · `field=value` — the value is ALWAYS literal text, as given: empty, `[ ] milk`, `true`, `{ok}` included;
  · `field:=<json>` — the only explicitly typed value (a list, a number, true/false/null, an object);
  · a non-text field the action DECLARES (`types`) is converted once by the widget door (`widgets.field_types`).
A field the action does not declare, or one given twice, is a refusal — and a refusal ENDS the command (rc≠0): it never
falls through to the bare-sentence or JSON paths (measured: `add_list name=[casa]` then created the list «name=[casa]»).
"""
from __future__ import annotations

import json


def _assigns(arg: str) -> bool:
    """`ident=…` or `ident:=…`: an argument that IS a field assignment (structure, no pattern)."""
    head, sep, _rest = str(arg).partition("=")
    head = head[:-1] if head.endswith(":") else head
    return bool(sep) and head.replace("-", "_").replace(".", "_").isidentifier()


def is_field_args(args: list[str]) -> bool:
    """On a line with one field assignment, there is no bare sentence."""
    return any(_assigns(a) for a in args)


def payload(spec: dict, args: list[str]) -> tuple[dict, str]:
    """`(payload, "")`, or `({}, why)` — the why is what the worker reads to write it right."""
    out: dict = {}
    for a in args:
        if not _assigns(a):
            return {}, f"`{a}` is not `field=value`: on a line of fields every argument is one"
        key, _sep, val = str(a).partition("=")
        typed = key.endswith(":")
        key = key[:-1] if typed else key
        if key not in spec:
            return {}, f"`{key}` is not a field of this action: {', '.join(spec) or 'it declares none'}"
        if key in out:
            return {}, f"`{key}` is given twice: give it once"
        if typed:
            try:
                out[key] = json.loads(val)
            except ValueError:
                return {}, f"`{key}:=` takes JSON, e.g. {key}:='[\"a\", \"b\"]', {key}:=true, {key}:=3"
        else:
            out[key] = val
    return out, ""

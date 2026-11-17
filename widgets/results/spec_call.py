"""widgets/results/spec_call.py — a layout named by a declared alias is that layout, for the act and its end state.

Demo sandbox 2026-11-17, S2: «compare them side by side» → `layout: "table"`, then `"side_by_side"`: refused, and «I
couldn't get that done» over the sheet on screen. The manifest declares the aliases (`widgets.enums`, V2-754); the act
and `spec.render` (through `spec_call`) read that one declaration. Unknown stays unknown: the card still refuses it."""
from widgets import enums as _enums, runtime as _rt


def layout_named(given: str) -> str:
    spec = ((((_rt.get("results") or {}).get("actions") or {}).get("layout") or {}).get("payload") or {}).get("layout")
    return _enums.resolve(str(spec or ""), str(given or "")) or str(given or "")


def spec_call(action: str, payload: dict) -> tuple[str, dict]:
    p = dict(payload or {})
    if action == "layout" and isinstance(p.get("layout"), str):
        p["layout"] = layout_named(p["layout"]).strip().lower()
    return action, p

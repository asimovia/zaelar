"""Every declared end state reads a field its app really has (operator, 2026-11-08).

The end state is declared by each app (`actions.<a>.done_when`) and the harness judges a request by it. A clause on a
field the view never carries does not fail loudly: `nucleo/truth.widget_field` returns None and the verdict is
«unverifiable» — the request is neither met nor unmet, nothing iterates, and «done» can never be checked. Measured
the same day: the music card's new `here` field returned {} when nothing played, so `here.title` was a missing key
and a failed start could never read unmet.

So the field a clause names must be a top-level key of the app's view, as its `golden.json` pins it
(`tests/widget_harness.py`: the SHAPE of `view_data()`, checked against the live view). Row clauses read the app's
stored collections (`widgets/rows.py`), not its view, and a clause with `absent_is` declares what absence means —
both are judged elsewhere.
"""
from __future__ import annotations

import json
from pathlib import Path

WIDGETS = Path("widgets")


def _clauses(dw):
    if isinstance(dw, list):
        for c in dw:
            yield from _clauses(c)
    elif isinstance(dw, dict):
        for mode in ("all", "any"):
            if isinstance(dw.get(mode), list):
                yield from _clauses(dw[mode])
                return
        yield dw


def _declared():
    for mf in sorted(WIDGETS.glob("*/manifest.json")):
        wid = mf.parent.name
        acts = json.loads(mf.read_text(encoding="utf-8")).get("actions") or {}
        for name, spec in acts.items():
            if isinstance(spec, dict) and spec.get("done_when"):
                for c in _clauses(spec["done_when"]):
                    yield wid, name, c


def test_every_end_state_clause_names_a_field_or_collection_of_its_apps_view():
    bad = []
    for wid, action, c in _declared():
        target = str(c.get("widget") or wid).split("::", 1)[0]
        if c.get("desktop") or c.get("canvas") or target != wid or c.get("collection") or "absent_is" in c:
            continue                                   # another kind of truth, rows, or a declared absence
        golden_p = WIDGETS / wid / "golden.json"
        if not golden_p.exists():
            continue
        shape = json.loads(golden_p.read_text(encoding="utf-8")).get("view_data_shape") or {}
        key = str(c.get("field") or "").split(".", 1)[0]
        if key and key not in shape:
            bad.append(f"{wid}:{action} → «{key}»")
    assert not bad, "clauses on a key the view does not carry (they can only read «unverifiable»): " + ", ".join(bad)
